import os
import feedparser
import json
import re
from datetime import datetime
from google import genai # Nueva librería oficial 2026

# Configuración con la nueva sintaxis
client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

def fetch_top_news():
    feeds = {
        'ES': [
            'https://www.abc.es/rss/2.0/espana/',
            'https://e00-elmundo.uecdn.es/elmundo/rss/espana.xml',
            'https://e00-expansion.uecdn.es/rss/portada.xml'
        ],
        'EU_UK': [
            'https://www.ft.com/?format=rss',
            'https://www.lesechos.fr/rss/rss_france.xml',
            'https://www.faz.net/rss/aktuell/',
            'https://www.lefigaro.fr/rss/figaro/actualites.xml'
        ],
        'USA_ROW': [
            'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
            'https://feeds.a.dj.com/rss/WSJBlog.xml'
        ]
    }
    
    collected_text = ""
    for region, urls in feeds.items():
        for url in urls:
            try:
                d = feedparser.parse(url)
                for entry in d.entries[:5]:
                    clean_desc = re.sub('<[^<]+?>', '', getattr(entry, 'description', ''))
                    collected_text += f"[{region}] {entry.title}: {clean_desc[:200]}\n"
            except:
                continue
    return collected_text

def analyze_with_ai(news_raw):
    prompt = f"""
    Actúa como Analista Jefe. Analiza estas noticias y genera un JSON:
    {news_raw}
    
    Formato JSON estricto:
    {{
      "espana": "Resumen España",
      "europa": "Resumen Europa",
      "global": "Resumen Global",
      "insight": "Frase de análisis profundo"
    }}
    """
    
    # Nueva sintaxis de llamada 2026
    response = client.models.generate_content(
        model="gemini-2.0-flash", # Usamos el modelo más reciente y rápido
        contents=prompt
    )
    
    try:
        # La nueva librería devuelve el objeto de forma más directa
        text_response = response.text
        json_match = re.search(r'\{.*\}', text_response, re.DOTALL)
        return json.loads(json_match.group(0))
    except Exception as e:
        print(f"Error: {e}")
        return {"espana": "Error", "europa": "Error", "global": "Error", "insight": "Error"}

def rewrite_html(data):
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            content = f.read()
        
        fecha_hoy = datetime.now().strftime("%d / %m / %Y")
        
        # Usamos un diccionario para asegurar que reemplazamos todo
        replacements = {
            "{{FECHA}}": fecha_hoy,
            "{{ES_CONTENT}}": data.get('espana', 'Sin datos'),
            "{{EU_CONTENT}}": data.get('europa', 'Sin datos'),
            "{{GL_CONTENT}}": data.get('global', 'Sin datos'),
            "{{IA_INSIGHT}}": data.get('insight', 'Sin datos')
        }
        
        for key, value in replacements.items():
            if key in content:
                content = content.replace(key, value)
            else:
                print(f"Advertencia: No se encontró el marcador {key}")

        with open("index.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("HTML actualizado con éxito.")
    except Exception as e:
        print(f"Error crítico en rewrite_html: {e}")
        
