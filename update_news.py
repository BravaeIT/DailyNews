import os
import feedparser
import json
import re
from datetime import datetime
from google import genai

# Configuración de Clave
api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def fetch_top_news():
    # Usamos fuentes RSS muy estables
    feeds = {
        'ES': ['https://e00-expansion.uecdn.es/rss/portada.xml'],
        'EU': ['https://www.ft.com/?format=rss'],
        'GL': ['https://rss.nytimes.com/services/xml/rss/nyt/World.xml']
    }
    text = ""
    for region, urls in feeds.items():
        for url in urls:
            try:
                d = feedparser.parse(url)
                for entry in d.entries[:5]:
                    text += f"[{region}] {entry.title}\n"
            except: continue
    return text

def analyze():
    raw_news = fetch_top_news()
    # Prompt reforzado para obligar a dar SOLO JSON
    prompt = f"""
    Genera un resumen ejecutivo de estas noticias:
    {raw_news}
    
    Responde UNICAMENTE con un objeto JSON siguiendo este esquema (sin texto extra):
    {{
      "espana": "Resumen corto de España",
      "europa": "Resumen corto de Europa",
      "global": "Resumen corto de Global",
      "insight": "Frase de análisis estratégico"
    }}
    """
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        # Limpieza profesional: busca el primer '{' y el último '}'
        text_response = response.text
        start = text_response.find('{')
        end = text_response.rfind('}') + 1
        json_str = text_response[start:end]
        return json.loads(json_str)
    except Exception as e:
        print(f"Error en IA: {e}")
        return {
            "espana": "Error al procesar noticias de España hoy.",
            "europa": "Error al procesar noticias de Europa.",
            "global": "Error al procesar noticias Globales.",
            "insight": "Reintentando conexión con fuentes de élite..."
        }

def run():
    data = analyze()
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    # Reemplazos con la fecha real
    html = html.replace("{{FECHA}}", datetime.now().strftime("%d / %m / %Y"))
    
    # IMPORTANTE: Si los placeholders ya fueron borrados, los buscamos por el texto que hay ahora
    # Pero para asegurar, simplemente sobreescribimos los campos clave.
    # Como la web ya tiene el texto de "Noticias de España...", vamos a buscar eso para cambiarlo.
    
    marcadores = {
        "Noticias de España disponibles en el link original.": data['espana'],
        "Actualidad europea en desarrollo.": data['europa'],
        "Mercados internacionales activos.": data['global'],
        "Análisis estratégico en curso.": data['insight']
    }
    
    for viejo, nuevo in marcadores.items():
        html = html.replace(viejo, nuevo)
        
    # Por si acaso aún quedan los originales
    html = html.replace("{{ES_CONTENT}}", data['espana'])
    html = html.replace("{{EU_CONTENT}}", data['europa'])
    html = html.replace("{{GL_CONTENT}}", data['global'])
    html = html.replace("{{IA_INSIGHT}}", data['insight'])

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
