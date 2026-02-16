import os
import feedparser
import json
import re
from datetime import datetime
from google import genai

# Configuración
client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

def fetch_top_news():
    feeds = {
        'ES': ['https://e00-expansion.uecdn.es/rss/portada.xml', 'https://e00-elmundo.uecdn.es/elmundo/rss/espana.xml'],
        'EU': ['https://www.ft.com/?format=rss', 'https://www.lesechos.fr/rss/rss_france.xml'],
        'GL': ['https://rss.nytimes.com/services/xml/rss/nyt/World.xml']
    }
    text = ""
    for region, urls in feeds.items():
        for url in urls:
            try:
                d = feedparser.parse(url)
                for entry in d.entries[:3]:
                    text += f"[{region}] {entry.title}\n"
            except: continue
    return text

def analyze():
    raw_news = fetch_top_news()
    prompt = f"Resume estas noticias en 4 secciones cortas: espana, europa, global e insight. Devuelve solo un JSON puro:\n{raw_news}"
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        # Limpieza de JSON
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        return json.loads(match.group(0))
    except:
        return {"espana": "Noticias de España disponibles en el link original.", 
                "europa": "Actualidad europea en desarrollo.", 
                "global": "Mercados internacionales activos.", 
                "insight": "Análisis estratégico en curso."}

def run():
    data = analyze()
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    # Reemplazos directos
    html = html.replace("{{FECHA}}", datetime.now().strftime("%d/%m/%Y"))
    html = html.replace("{{ES_CONTENT}}", data.get('espana', ''))
    html = html.replace("{{EU_CONTENT}}", data.get('europa', ''))
    html = html.replace("{{GL_CONTENT}}", data.get('global', ''))
    html = html.replace("{{IA_INSIGHT}}", data.get('insight', ''))
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
    
        
