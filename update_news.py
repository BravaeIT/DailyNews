import os, feedparser
from datetime import datetime
from google import genai

client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))

def fetch_top_news():
    feeds = {'ES': 'https://e00-expansion.uecdn.es/rss/portada.xml',
             'UK': 'https://www.ft.com/?format=rss',
             'GL': 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml'}
    text = ""
    for reg, url in feeds.items():
        try:
            d = feedparser.parse(url)
            text += f"REGION {reg}: " + " | ".join([e.title for e in d.entries[:3]]) + ". "
        except: continue
    return text

def run():
    raw_news = fetch_top_news()
    # Pedimos una lista simple separada por asteriscos
    prompt = f"Analiza estas noticias y haz 4 párrafos cortos (España, Europa, Global, Insight). Separa cada párrafo UNICAMENTE con el símbolo '$'. No pongas títulos. Noticias: {raw_news}"
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
        partes = response.split('$')
        # Si la IA nos da al menos las 4 partes, las usamos. Si no, al backup.
        es = partes[0].strip() if len(partes) > 0 else "Actualidad española en curso."
        eu = partes[1].strip() if len(partes) > 1 else "Actualidad europea en curso."
        gl = partes[2].strip() if len(partes) > 2 else "Actualidad internacional en curso."
        ia = partes[3].strip() if len(partes) > 3 else "Analizando implicaciones estratégicas."
    except:
        es, eu, gl, ia = "Error de conexión con la IA.", "Reintentando...", "Reintentando...", "Reintentando..."

    with open("template.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    html = html.replace("{{FECHA}}", datetime.now().strftime("%d / %m / %Y"))
    html = html.replace("{{ES_CONTENT}}", es)
    html = html.replace("{{EU_CONTENT}}", eu)
    html = html.replace("{{GL_CONTENT}}", gl)
    html = html.replace("{{IA_INSIGHT}}", ia)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
