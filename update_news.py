import os
import google.generativeai as genai
import feedparser
import json
import re
from datetime import datetime

# 1. Configuración de API con el modelo más capaz para razonamiento
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

def fetch_top_news():
    # Definición de RSS de tus medios preferidos (ES, UK, FR, DE, USA)
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
            'https://feeds.a.dj.com/rss/WSJBlog.xml',
            'https://www.economist.com/the-world-this-week/rss.xml'
        ]
    }
    
    collected_text = ""
    for region, urls in feeds.items():
        for url in urls:
            try:
                # User-agent para evitar bloqueos básicos de seguridad
                d = feedparser.parse(url)
                for entry in d.entries[:5]:
                    # Limpiamos etiquetas HTML de las descripciones si las hay
                    clean_desc = re.sub('<[^<]+?>', '', entry.description)
                    collected_text += f"[{region}] SOURCE: {url} | TITLE: {entry.title} | BODY: {clean_desc[:300]}\n"
            except Exception as e:
                print(f"Error leyendo {url}: {e}")
                continue
    return collected_text

def analyze_with_ai(news_raw):
    # Prompt diseñado para deduplicación y análisis trilingüe
    prompt = f"""
    Actúa como un Analista Jefe de Inteligencia Económica. Tu objetivo es redactar el Briefing Diario para un comité de dirección.
    
    DATOS DE ENTRADA (Noticias en ES, EN, FR, DE):
    {news_raw}
    
    INSTRUCCIONES CRÍTICAS:
    1. DEDUPLICACIÓN: Si varias fuentes hablan del mismo evento (ej. BCE, Wall Street, Ucrania), consolida la información en un solo párrafo coherente. No repitas la misma noticia en secciones diferentes.
    2. FILTRO DE CALIDAD: Prioriza noticias de calado económico y político. Ignora sucesos menores o deportes.
    3. TRADUCCIÓN: Traduce mentalmente del inglés, francés y alemán, pero redacta TODO en un español elegante y ejecutivo.
    4. FORMATO: Devuelve UNICAMENTE un objeto JSON válido con estas llaves:
       - "espana": Resumen ejecutivo de lo más relevante en España.
       - "europa": Resumen de UK, Francia, Alemania y la UE.
       - "global": Resumen de USA y mercados internacionales.
       - "insight": Un análisis transversal de 1 sola frase que conecte puntos entre regiones.
    """
    
    response = model.generate_content(prompt)
    
    # Limpieza estricta de la respuesta para extraer el JSON
    raw_response = response.text
    try:
        # Buscamos el bloque JSON por si la IA añade explicaciones
        json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if json_match:
            clean_json = json_match.group(0)
            return json.loads(clean_json)
        else:
            raise ValueError("No se encontró JSON en la respuesta de la IA")
    except Exception as e:
        print(f"Error parseando respuesta de IA: {e}")
        # Fallback por si falla el JSON
        return {
            "espana": "Error procesando noticias hoy.",
            "europa": "Error de sincronización.",
            "global": "Consultar fuentes manuales.",
            "insight": "Sistema en mantenimiento."
        }

def rewrite_html(data):
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            content = f.read()
        
        # Fecha actual en formato profesional
        fecha_hoy = datetime.now().strftime("%d de %B, %Y")
        
        # Inyección de datos mediante reemplazo de placeholders
        content = content.replace("{{FECHA}}", fecha_hoy)
        content = content.replace("{{ES_CONTENT}}", data['espana'])
        content = content.replace("{{EU_CONTENT}}", data['europa'])
        content = content.replace("{{GL_CONTENT}}", data['global'])
        content = content.replace("{{IA_INSIGHT}}", data['insight'])
        
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("HTML actualizado correctamente.")
    except Exception as e:
        print(f"Error escribiendo el HTML: {e}")

if __name__ == "__main__":
    print(f"--- Iniciando proceso: {datetime.now()} ---")
    raw_data = fetch_top_news()
    if raw_data:
        analysis = analyze_with_ai(raw_data)
        rewrite_html(analysis)
    else:
        print("No se pudieron obtener noticias de las fuentes RSS.")
    print("--- Proceso finalizado ---")
