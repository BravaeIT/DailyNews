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
    feeds = {
        'ES': 'https://e00-expansion.uecdn.es/rss/portada.xml',
        'UK': 'https://www.ft.com/?format=rss',
        'GL': 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml'
    }
    text = ""
    for region, url in feeds.items():
        try:
            d = feedparser.parse(url)
            for entry in d.entries[:5]:
                text += f"[{region}] {entry.title}. "
        except: continue
    return text

def analyze():
    raw_news = fetch_top_news()
    # Prompt ultra-directo para evitar que la IA charle
    prompt = f"Analiza: {raw_news}. Genera un JSON con llaves 'espana', 'europa', 'global', 'insight'. Sé breve. Solo JSON, nada de texto antes o después."
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        res_text = response.text
        print(f"Respuesta IA: {res_text}") # Esto saldrá en tu log de GitHub
        
        # Buscamos el JSON incluso si la IA se pone creativa
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("JSON no encontrado")
    except Exception as e:
        print(f"Fallo en análisis: {e}")
        # Retornamos algo dinámico aunque sea el plan B
        return {
            "espana": f"Última hora: Revisando titulares de Expansión a las {datetime.now().strftime('%H:%M')}.",
            "europa": "Análisis de Financial Times en proceso de síntesis.",
            "global": "Monitorizando apertura de mercados internacionales.",
            "insight": "Sesión marcada por la espera de datos macroeconómicos clave."
        }

def run():
    data = analyze()
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    # Ponemos la fecha
    html = html.replace("{{FECHA}}", datetime.now().strftime("%d/%m/%Y"))
    
    # Diccionario de búsqueda agresiva (borra lo viejo y pone lo nuevo)
    mapeo = {
        "espana": ["{{ES_CONTENT}}", "Ibex 35 y principales valores en fase de actualización matinal.", "Actualizando..."],
        "europa": ["{{EU_CONTENT}}", "Mercados europeos analizando la apertura y tipos de interés.", "Actualizando..."],
        "global": ["{{GL_CONTENT}}", "Wall Street y Asia marcan la tendencia de la jornada.", "Actualizando..."],
        "insight": ["{{IA_INSIGHT}}", "Volatilidad moderada en los mercados internacionales hoy.", "Actualizando..."]
    }
    
    for clave, viejos_textos in mapeo.items():
        for viejo in viejos_textos:
            if viejo in html:
                html = html.replace(viejo, data[clave])

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
