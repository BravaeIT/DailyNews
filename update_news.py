import os
import re
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher
from pydantic import BaseModel, Field
from typing import List
from google.genai import types


import requests
import feedparser
from google import genai

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
TZ = ZoneInfo("Europe/Madrid")

# Feeds “prácticos” (RSS real). Ajusta a tu gusto.
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
    # EN
    "election", "government", "parliament", "fed", "inflation", "rates", "debt", "deficit",
    "budget", "tariff", "economy", "markets",
    # FR/DE (mínimo)
    "élection", "gouvernement", "inflation", "taux", "budget", "économie", "marchés",
]

UA = "Mozilla/5.0 (compatible; DailyBriefBot/1.0; +https://github.com/)"

class Link(BaseModel):
    title: str
    source: str
    url: str

class Section(BaseModel):
    summary: str = Field(description="2–4 sentences, politics/economy focus.")
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

def fetch_entries(source: str, url: str, region: str, limit: int = 20):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        d = feedparser.parse(r.content)
        out = []
        for e in d.entries[:limit]:
            title = (getattr(e, "title", "") or "").strip()
            link = canonical_url(getattr(e, "link", "") or "")
            published = getattr(e, "published", "") or getattr(e, "updated", "") or ""
            out.append({
                "region": region,
                "source": source,
                "title": title,
                "url": link,
                "published": published,
            })
        return out
    except Exception as ex:
        logging.warning("Feed fail: %s (%s) -> %s", source, url, ex)
        return []

def keyword_score(title: str) -> int:
    lt = (title or "").lower()
    return sum(1 for k in KEYWORDS if k in lt)

def dedupe_items(items):
    # 1) dedupe por URL canónica
    by_url = {}
    for it in items:
        u = it["url"]
        if not u:
            continue
        by_url.setdefault(u, it)

    # 2) dedupe fuzzy por título dentro de cada región
    final = []
    seen_titles = {r: [] for r in FEEDS.keys()}
    for it in by_url.values():
        rt = norm_title(it["title"])
        reg = it["region"]
        dup = any(similar(rt, t) > 0.92 for t in seen_titles.get(reg, []))
        if dup:
            continue
        seen_titles.setdefault(reg, []).append(rt)
        final.append(it)

    # prioriza política/economía (sin matar todo)
    final.sort(key=lambda x: (x["region"], -keyword_score(x["title"])))
    return final

def extract_first_json(text: str):
    # intenta encontrar el primer bloque JSON válido en la respuesta
    if not text:
        return None
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

def build_prompt(items, date_str):
    # reducimos a lo esencial para el LLM
    payload = {
        "date": date_str,
        "items": items[:60],  # cap para no inflar tokens
        "required_sections": ["spain", "europe_uk", "usa", "row", "insight"],
        "languages": LANGS,
    }
    return f"""
You are an elite news editor. Produce a multilingual intelligence brief focused on politics & economics.
Rules:
- Output STRICT valid JSON only. No markdown. No commentary.
- Avoid duplicate stories: consolidate across sources.
- Each section summary: 2–4 sentences, dense and analytical, no hype.
- Include sources: for each section, provide up to 5 links as objects {{title, source, url}}.
- Keep article titles as-is (original language). Do not invent facts beyond the headlines provided.

Return JSON with this shape:
{{
  "es": {{"spain": {{"summary": "...", "links":[...] }}, "europe_uk": ..., "usa": ..., "row": ..., "insight": ...}},
  "en": {{...}},
  "fr": {{...}}
}}

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
        li.append(f'<li><a class="hover:underline" href="{url}" target="_blank" rel="noreferrer">{title}</a> <span class="text-zinc-600">· {src}</span></li>')
    if not li:
        return ""
    return '<ul class="mt-3 space-y-1 text-xs text-zinc-500">' + "".join(li) + "</ul>"

def render(template: str, mapping: dict) -> str:
    out = template
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    return out

def build_page(lang, brief_lang, template_html, date_str):
    # brief_lang: dict con secciones
    def sec(key):
        return brief_lang.get(key, {}) if isinstance(brief_lang.get(key, {}), dict) else {}

    sp = sec("spain")
    eu = sec("europe_uk")
    us = sec("usa")
    rw = sec("row")
    ins = sec("insight")

    mapping = {
        "FECHA": date_str,
        "LANG": lang.upper(),
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
    # fallback visual si viene vacío
    for k in ["SPAIN_CONTENT","EU_CONTENT","USA_CONTENT","ROW_CONTENT","IA_INSIGHT"]:
        if not mapping[k]:
            mapping[k] = "Sin señal suficiente hoy (feed/LLM). Revisa logs."

    return render(template_html, mapping)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="public")
    args = ap.parse_args()

    now = datetime.now(TZ)
    date_str = now.strftime("%d / %m / %Y")

    # 1) recolecta
    all_items = []
    for region, feeds in FEEDS.items():
        for source, url in feeds:
            all_items.extend(fetch_entries(source, url, region))

    items = dedupe_items(all_items)
    logging.info("Collected=%d, after dedupe=%d", len(all_items), len(items))

    # 2) llama LLM (si hay API key)
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    logging.info("Gemini API key present: %s", "yes" if api_key else "no")

    brief = None
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
    
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,  # tu prompt con el payload de items
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Brief,
                    temperature=0.3,
                    max_output_tokens=1800,
                ),
            )

        # Si el modelo respeta el schema, esto ya viene parseado:
        brief = response.parsed  # -> instancia Brief (pydantic)
        logging.info("LLM parsed OK")

    except Exception as ex:
        logging.exception("LLM call/parse failed: %s", ex) 
    
    # 3) fallback sin LLM: bullets por región
    if not brief:
        def top_links(region):
            out = []
            for it in items:
                if it["region"] == region:
                    out.append({"title": it["title"], "source": it["source"], "url": it["url"]})
                if len(out) >= 5:
                    break
            return out

        brief = {}
        for lang in LANGS:
            brief[lang] = {
                "spain": {"summary": "Titulares principales (fallback).", "links": top_links("spain")},
                "europe_uk": {"summary": "Titulares principales (fallback).", "links": top_links("europe_uk")},
                "usa": {"summary": "Titulares principales (fallback).", "links": top_links("usa")},
                "row": {"summary": "Titulares principales (fallback).", "links": top_links("row")},
                "insight": {"summary": "Insight no disponible sin LLM.", "links": []},
            }

    # 4) render HTML
    template_path = Path("template.html")
    template_html = template_path.read_text(encoding="utf-8")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    for lang in LANGS:
        lang_dir = outdir if lang == "es" else (outdir / lang)
        lang_dir.mkdir(parents=True, exist_ok=True)

        page = build_page(lang, brief.get(lang, {}), template_html, date_str)
        (lang_dir / "index.html").write_text(page, encoding="utf-8")
        logging.info("Wrote %s", str(lang_dir / "index.html"))

if __name__ == "__main__":
    main()
