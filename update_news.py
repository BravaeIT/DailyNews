import os
import google.generativeai as genai
import feedparser
import json
from datetime import datetime

# Configuración IA
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash') # Usamos 1.5 para mayor ventana de contexto

def fetch_news():
    feeds = {
        'ES': ['https://www.abc.es/rss/2.0/espana/', 'https://e00-elmundo.uecdn.es/elmundo/rss/espana.xml', 'https://e00-expansion.uecdn.es/rss/portada.xml'],
        'EU/UK': ['https://www.ft.com/?format=rss', 'https://www.lesechos.fr/rss/rss_france.xml', 'https://www.faz.net/rss/aktuell/'],
        'USA': ['https://feeds.a.dj.com/rss/WSJBlog.xml', 'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml']
    }
    
    raw_data = ""
    for region, urls in feeds.items():
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:4]:
                    raw_data += f"[{region}] {entry.title}: {entry.description}\n"
            except:
                continue
    return raw_data

def generate_brief(news_content):
    prompt = f"""
    Eres un analista de inteligencia para un C-level. 
    Aquí tienes las noticias frescas de hoy:
    {news_content}
    
    TAREA:
    1. Filtra noticias duplicadas. Si varias fuentes hablan de lo mismo, consolida la información.
    2. Traduce y sintetiza fuentes de FR, DE, UK y USA.
    3. Formatea la salida estrictamente en JSON con este esquema:
    {{
      "espana": "Resumen ejecutivo de España",
      "europa": "Resumen de UK, Francia, Alemania y UE",
      "global": "Resumen de USA y resto del mundo",
      "insight": "Análisis geopolítico/económico cruzado de una frase"
    }}
    Usa un tono sobrio y profesional.
    """
    
    response = model.generate_content(prompt)
    # Extraer solo el JSON (a veces la IA pone bloques de código ```json)
    content = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(content)

def update_web(data):
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    # Actualizar fecha
    hoy = datetime.now().strftime("%d %b %Y")
    
    # Inyectar datos en el HTML usando marcadores de posición simples
    # (Asegúrate de que tu index.html tenga estos IDs o marcadores)
    html = html.replace("{{FECHA}}", hoy)
    html = html.replace("{{ES_CONTENT}}", data['espana'])
    html = html.replace("{{EU_CONTENT}}", data['europa'])
    html = html.replace("{{GL_CONTENT}}", data['global'])
    html = html.replace("{{IA_INSIGHT}}", data['insight'])
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    print("Capturando noticias de fuentes de élite...")
    raw_news = fetch_news()
    print("Analizando y deduplicando con Gemini...")
    brief_data = generate_brief(raw_news)
    print("Actualizando interfaz web...")
    update_web(brief_data)
    print("Misión cumplida.")
