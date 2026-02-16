import os
import re
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher
from typing import List

import requests
import feedparser
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
TZ = ZoneInfo("Europe/Madrid")
UA = "Mozilla/5.0 (compatible; DailyBriefBot/1.0; +https://github.com/)"

FEEDS = {
    "spain": [
        ("Expansión", "https://e00-expansion.uecdn.es/rss/portada.xml"),
        ("El Mundo", "http://www.elmundo.es/elmundo/rss/portada.xml"),
        ("ABC", "http://www.abc.es/rss/feeds/abc_ultima.xml"),
    ],
    "europe_uk": [
        ("FAZ", "https://www.faz.net/rss/aktuell"),
        ("Le Figaro", "https://www.lefigaro.fr/rss/figaro_actualites.xml"),
        ("Les Echos (Economie)", "https://services.lesechos.fr/rss/les-echos-economie.xml"),
    ],
    "usa": [
        ("WSJ World", "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
        ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
        ("NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
        ("NYT Politics", "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"),
    ],
    "row": [
        ("NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ],
}

LANGS = ["es", "en", "fr"]

KEYWORDS = [
    # ES
    "gobierno", "elecciones", "parlamento", "congreso", "senado", "bce", "banco central",
    "inflación", "tipos", "deuda", "déficit", "presupuesto", "impuestos", "arancel",
    "economía", "mercados", "ibex", "bolsa",
    # EN
    "election", "government", "parliament", "fed", "inflation", "rates", "debt", "deficit",
    "budget", "tariff", "economy", "markets", "bond", "yields",
    # FR
    "élection", "gouvernement", "inflation", "taux", "budget", "économie", "marchés",
]

# ---------- Pydantic schema (LLM output) ----------
class Link(BaseModel):
    title: str
    source: str
    url: str

class Section(BaseModel):
    summary: str = Field(description="2–4 sentences; politics & economics focus; analytical; no hype.")
    links: List[Link] = []

class BriefLang(BaseModel):
    spain: Section
    europe_uk: Section
    usa: Section
    row: Section
    insight: Section

class Brief(BaseModel):
    es: BriefLang
    en: BriefLang
    fr: BriefLang
# -------------------------------------------------


def norm_title(t: str) -> str:
    t = (t or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s\-]", "", t)
    return t[:300]

def canonical_url(u: str) -> str:
    if not u:
        return ""
    u = u.strip()
    u = u.split("#", 1)[0]
    u = u.split("?", 1)[0]
    return u.rstrip("/")

def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def keyword_score(title: str) -> int:
    lt = (title or "").lower()
    return sum(1 for k in KEYWORDS if k in lt)

def fetch_entries(source: str, url: str, region: str, limit: int = 25):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        d = feedparser.parse(r.content)
        out = []
        for e in d.entries[:limit]:
            title = (getattr(e, "title", "") or "").strip()
            link = canonical_url(getattr(e, "link", "") or "")
            published = getattr(e, "published", "") or getattr(e, "updated", "") or ""
            if not title:
                continue
            out.append({
                "region": region,
                "source": source,
                "title": title,
                "url": link,
                "published": published,
                "score": keyword_score(title),
            })
        return out
    except Exception as ex:
        logging.warning("Feed fail: %s (%s) -> %s", source, url, ex)
        return []

def dedupe_items(items):
    # 1) dedupe by URL
    by_url = {}
    for it in items:
        u = it["url"]
        if u:
            by_url.setdefault(u, it)

    # 2) fuzzy dedupe by title within region
    final = []
    seen = {}
    for it in by_url.values():
        reg = it["region"]
        rt = norm_title(it["title"])
        seen.setdefault(reg, [])
        if any(similar(rt, t) > 0.92 for t in seen[reg]):
            continue
        seen[reg].append(rt)
        final.append(it)

    # prioritize politics/econ score within region
    final.sort(key=lambda x: (x["region"], -x["score"]))
    return final

def top_links(items, region, k=5):
    cand = [it for it in items if it["region"] == region]
    cand.sort(key=lambda x: -x["score"])

    filtered = [it for it in cand if it["score"] > 0]
    use = filtered if len(filtered) >= min(3, k) else cand

    out = []
    for it in use[:k]:
        if it["url"]:
            out.append({"title": it["title"], "source": it["source"], "url": it["url"]})
    return out

def build_prompt(items, date_str):
    payload = {
        "date": date_str,
        "items": [
            {k: it[k] for k in ["region", "source", "title", "url", "published"]}
            for it in items[:70]
        ],
    }
    return f"""
You are an elite news editor. Produce a multilingual intelligence brief focused on politics & economics.
Rules:
- Use ONLY the headlines and sources provided. Do NOT invent facts beyond them.
- Consolidate duplicates across sources; prefer top-tier outlets.
- For each section: 2–4 sentences, dense and analytical, no hype.
- Include up to 5 links per section as objects: {{title, source, url}}.
- Output MUST be strict JSON matching the provided schema.

Data:
{json.dumps(payload, ensure_ascii=False)}
""".strip()

def links_html(links):
    if not links:
        return ""
    li = []
    for x in links[:5]:
        title = (x.get("title") or "").strip()
        src = (x.get("source") or "").strip()
        url = (x.get("url") or "").strip()
        if not (title and url):
            continue
        li.append(
            f'<li><a class="hover:underline" href="{url}" target="_blank" rel="noreferrer">{title}</a> '
            f'<span class="text-zinc-600">· {src}</span></li>'
        )
    if not li:
        return ""
    return '<ul class="mt-3 space-y-1 text-xs text-zinc-500">' + "".join(li) + "</ul>"

def render(template: str, mapping: dict) -> str:
    out = template
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    return out

def nav_hrefs(lang: str):
    # Works for GitHub Pages root OR project pages. All relative.
    if lang == "es":
        return {"HREF_ES": "./", "HREF_EN": "en/", "HREF_FR": "fr/"}
    if lang == "en":
        return {"HREF_ES": "../", "HREF_EN": "./", "HREF_FR": "../fr/"}
    return {"HREF_ES": "../", "HREF_EN": "../en/", "HREF_FR": "./"}  # fr

def build_page(lang, brief_lang_dict, template_html, date_str):
    def sec(key):
        v = brief_lang_dict.get(key, {})
        return v if isinstance(v, dict) else {}

    sp = sec("spain")
    eu = sec("europe_uk")
    us = sec("usa")
    rw = sec("row")
    ins = sec("insight")

    mapping = {
        "FECHA": date_str,
        "LANG": lang.upper(),
        "HTML_LANG": lang,
        **nav_hrefs(lang),

        "SPAIN_CONTENT": (sp.get("summary") or "").strip(),
        "EU_CONTENT": (eu.get("summary") or "").strip(),
        "USA_CONTENT": (us.get("summary") or "").strip(),
        "ROW_CONTENT": (rw.get("summary") or "").strip(),
        "IA_INSIGHT": (ins.get("summary") or "").strip(),

        "SPAIN_LINKS": links_html(sp.get("links") or []),
        "EU_LINKS": links_html(eu.get("links") or []),
        "USA_LINKS": links_html(us.get("links") or []),
        "ROW_LINKS": links_html(rw.get("links") or []),
    }

    for k in ["SPAIN_CONTENT", "EU_CONTENT", "USA_CONTENT", "ROW_CONTENT", "IA_INSIGHT"]:
        if not mapping[k]:
            mapping[k] = "Sin señal suficiente hoy (feed/LLM). Revisa logs."

    return render(template_html, mapping)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="public")
    args = ap.parse_args()

    now = datetime.now(TZ)
    date_str = now.strftime("%d / %m / %Y")

    # 1) collect
    all_items = []
    for region, feeds in FEEDS.items():
        for source, url in feeds:
            all_items.extend(fetch_entries(source, url, region))

    items = dedupe_items(all_items)
    logging.info("Collected=%d, after dedupe=%d", len(all_items), len(items))

    # 2) LLM (JSON mode + schema)
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    logging.info("Gemini API key present: %s", "yes" if api_key else "no")

    brief_dict = None
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = build_prompt(items, date_str)

            resp = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Brief,
                    temperature=0.3,
                    max_output_tokens=2000,
                ),
            )

            brief_obj = resp.parsed  # Pydantic Brief
            brief_dict = brief_obj.model_dump()
            logging.info("LLM parsed OK")

        except Exception as ex:
            logging.exception("LLM call/parse failed: %s", ex)

    # 3) fallback
    if not brief_dict:
        logging.warning("FALLBACK mode (no LLM or parse failure)")
        brief_dict = {}
        for lang in LANGS:
            brief_dict[lang] = {
                "spain": {"summary": "Titulares principales (fallback).", "links": top_links(items, "spain")},
                "europe_uk": {"summary": "Titulares principales (fallback).", "links": top_links(items, "europe_uk")},
                "usa": {"summary": "Titulares principales (fallback).", "links": top_links(items, "usa")},
                "row": {"summary": "Titulares principales (fallback).", "links": top_links(items, "row")},
                "insight": {"summary": "Insight no disponible sin LLM.", "links": []},
            }

    # 4) render
    template_html = Path("template.html").read_text(encoding="utf-8")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    for lang in LANGS:
        lang_dir = outdir if lang == "es" else (outdir / lang)
        lang_dir.mkdir(parents=True, exist_ok=True)

        page = build_page(lang, brief_dict.get(lang, {}), template_html, date_str)
        (lang_dir / "index.html").write_text(page, encoding="utf-8")
        logging.info("Wrote %s", str(lang_dir / "index.html"))

if __name__ == "__main__":
    main()
