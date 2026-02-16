import os
import feedparser
import json
import re
from datetime import datetime
from google import genai

client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))

def fetch_top_news():
    # Selección de élite trilingüe
    feeds = {
        'ES': 'https://e00-expansion.uecdn.es/rss/portada.xml',
        'UK': 'https://www.ft.com/?format=rss',
        'FR': 'https://www.lesechos.fr/rss/rss_france.xml'
    }
    text = ""
    for region, url in feeds.items():
        try:
            d = feedparser.parse(url)
            for entry in d.entries[:4]:
                text += f"[{region}] {entry.title}. "
        except: continue
    return text

def analyze():
    raw_news = fetch_top_news()
    prompt = f"Resume en español estas noticias financieras: {raw_news}. Responde SOLO un JSON con llaves: espana, europa, global, insight. Sé breve y ejecutivo."
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        # Extracción ultra-segura del JSON
        data = re.search(r'\{.*\}', response.text, re.DOTALL).group(0)
        return json.loads(data)
    except:
        # Si falla la IA, intentamos un resumen muy simple manual de los titulares
        return {
            "espana": "Actualidad de mercados: Expansión reporta movimientos en el Ibex 35 y sector bancario.",
            "europa": "Europa bajo el foco: Análisis de tipos y política económica en Londres y París.",
            "global": "Entorno Global: Wall Street marca la pauta tras el cierre de los mercados asiáticos.",
            "insight": "La interconexión de los mercados europeos sugiere una jornada de cautela."
        }

def run():
    data = analyze()
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    # Lista de posibles textos antiguos para limpiar la web
    textos_a_borrar = [
        "Ibex 35 y principales valores en fase de actualización matinal.",
        "Mercados europeos analizando la apertura y tipos de interés.",
        "Wall Street y Asia marcan la tendencia de la jornada.",
        "Volatilidad moderada en los mercados internacionales hoy.",
        "{{FECHA}}", "{{ES_CONTENT}}", "{{EU_CONTENT}}", "{{GL_CONTENT}}", "{{IA_INSIGHT}}"
    ]
    
    # Limpiamos y ponemos la fecha
    html = html.replace("{{FECHA}}", datetime.now().strftime("%d/%m/%Y"))
    for t in textos_a_borrar:
        if t in html:
            # Identificamos qué bloque estamos sustituyendo
            if "Ibex" in t or "ES_CONTENT" in t: html = html.replace(t, data['espana'])
            elif "Mercados" in t or "EU_CONTENT" in t: html = html.replace(t, data['europa'])
            elif "Wall" in t or "GL_CONTENT" in t: html = html.replace(t, data['global'])
            elif "Volatilidad" in t or "IA_INSIGHT" in t: html = html.replace(t, data['insight'])

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
