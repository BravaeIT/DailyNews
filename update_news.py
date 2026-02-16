import os, feedparser, re, json
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
            text += f"REGION {reg}: " + " | ".join([e.title for e in d.entries[:3]]) + "\n"
        except: continue
    return text

def run():
    raw_news = fetch_top_news()
    prompt = f"Analiza estas noticias y genera 4 párrafos cortos. Empieza cada párrafo con 'TEXTO1:', 'TEXTO2:', 'TEXTO3:' y 'TEXTO4:'. Noticias: {raw_news}"
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
        es = re.search(r'TEXTO1:(.*?)TEXTO2:', response, re.S).group(1).strip()
        eu = re.search(r'TEXTO2:(.*?)TEXTO3:', response, re.S).group(1).strip()
        gl = re.search(r'TEXTO3:(.*?)TEXTO4:', response, re.S).group(1).strip()
        ia = re.search(r'TEXTO4:(.*)', response, re.S).group(1).strip()
    except:
        es, eu, gl, ia = "Sincronizando España...", "Sincronizando Europa...", "Sincronizando Global...", "Analizando tendencia..."

    # LEER LA PLANTILLA (HTML PURO)
    with open("template.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    # REEMPLAZAR MARCADORES
    html = html.replace("{{FECHA}}", datetime.now().strftime("%d / %m / %Y"))
    html = html.replace("{{ES_CONTENT}}", es)
    html = html.replace("{{EU_CONTENT}}", eu)
    html = html.replace("{{GL_CONTENT}}", gl)
    html = html.replace("{{IA_INSIGHT}}", ia)

    # ESCRIBIR RESULTADO
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
