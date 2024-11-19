import os
import wikipedia
import pandas as pd
from flask import Flask, jsonify
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from feedgen.feed import FeedGenerator
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime

# Initialize FastAPI app and templates
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# MongoDB connection using environment variables
mongo_client = MongoClient(os.environ.get("MONGODB_URI"), server_api=ServerApi('1'))
db = mongo_client[os.environ.get("DATABASE_NAME")]
collection = db[os.environ.get("COLLECTION_NAME")]
airport_collection = db[os.environ.get("AIRPORT_COLLECTION_NAME")]

all_documents = list(airport_collection.find())
airport_df = pd.DataFrame(all_documents)

def fetch_airport_data(iata_code):
    """Fetch airport data from MongoDB based on IATA code."""
    try:
        # MongoDB'den havalimanı verisini al
        airport_data = airport_collection.find_one({"IATACode": iata_code})
        if not airport_data:
            return pd.DataFrame()
        
        # MongoDB verisini DataFrame'e dönüştür
        df = pd.DataFrame([{
            'IATACode': airport_data['IATACode'],
            'AirportName': airport_data['AirportName'],
            'City': airport_data['City'],
            'Country': airport_data['CountryName'],
            'tagList': airport_data.get('tagList', '')
        }])
        return df
    except Exception as e:
        print(f"Havalimanı verisi alınırken hata oluştu: {e}")
        return pd.DataFrame()

def get_tags_from_airport_data(airport_df):
    """Extract tags from airport data."""
    if airport_df.empty:
        return []
    tag_list = airport_df['tagList'].values[0]
    return tag_list.split(', ')

def query_documents_by_tags(tags):
    """Query MongoDB documents that match any of the provided tags."""
    query = {'$or': [{'Body': {'$regex': tag, '$options': 'i'}} for tag in tags]}
    return list(collection.find(query))

def add_matched_tags_to_items(filtered_items, tags):
    """Add matched tags to each item in the filtered items."""
    for item in filtered_items:
        matched_tags = [tag for tag in tags if tag.lower() in item['Body'].lower()]
        item['matched_tags'] = matched_tags
    return filtered_items

def get_data_from_source(iata_code=None):
    """Fetch data from MongoDB based on the provided IATA code."""
    if not iata_code:
        return []
    
    airport_df = fetch_airport_data(iata_code)
    tags = get_tags_from_airport_data(airport_df)
    filtered_items = query_documents_by_tags(tags)

    return add_matched_tags_to_items(filtered_items, tags)

@app.get("/rss/{iata_code}")
def generate_rss_feed(iata_code: str):
    """Generate RSS feed for the given IATA code."""
    fg = FeedGenerator()
    fg.title(f'{iata_code} Havalimani RSS Beslemesi')
    fg.link(href=f'https://aviarss.onrender.com/rss/{iata_code}', rel='self')
    fg.link(href='https://aviarss.onrender.com', rel='alternate')
    fg.description(f'{iata_code} havalimani ile ilgili haberler ve guncellemeler')
    fg.language('tr')
    fg.lastBuildDate()
    fg.generator('AviRSS Feed Generator')

    items = get_data_from_source(iata_code)

    if not items:
        raise HTTPException(status_code=404, detail="Belirtilen IATA kodu için öğe bulunamadı")

    for item in items:
        add_item_to_feed(fg, item)

    rss_feed = fg.rss_str(pretty=True)

    # Fetch Wikipedia summary
    try:
        summary = wikipedia.summary(wikipedia.search(f"IATA:{iata_code} airport")[0]).strip()
    except Exception as e:
        summary = "No summary available."
        
    # Create a response dictionary
    response_data = {
        'rss_feed': rss_feed,
        'summary': summary
    }
    return jsonify(response_data)

def calculate_reading_time(text):
    """
    Metni okumak için gereken tahmini süreyi hesaplar.
    Ortalama okuma hizi: 185 kelime/dakika
    Cikti formati: X dakika Y saniye
    """
    words = len(text.split())
    total_minutes = words / 185  # Dakikada 185 kelime okunduğunu varsayıyoruz
    
    # Tam dakika ve saniye hesaplama
    minutes = int(total_minutes)
    seconds = int((total_minutes - minutes) * 60)
    
    if minutes == 0 and seconds < 30:
        return "30 saniyeden az"
    elif minutes == 0:
        return f"{seconds} saniye"
    elif seconds == 0:
        return f"{minutes} dakika"
    else:
        return f"{minutes} dk {seconds} sn"

def add_item_to_feed(fg, item):
    """Add a single item to the RSS feed."""
    fe = fg.add_entry()
    fe.title(str(item['Title']))
    fe.link(href=str(item['Link']))
    
    # Yazar bilgisi ekleme
    if 'Author' in item and item['Author']:
        fe.author({'name': item['Author']})
    else:
        fe.author({'name': 'AviRSS'})

    body_text = str(item['Body'])

    # Tahmini okuma süresini hesapla
    reading_time = calculate_reading_time(item['Title'] + " " + body_text)
    
    if 'matched_tags' in item and item['matched_tags']:
        for tag in item['matched_tags']:
            body_text = body_text.replace(tag, f"<strong><u>{tag}</u></strong>")
        tags_str = ', '.join(item['matched_tags'])
        body_text += f"<hr/><br/><br/><strong>Eşleşen Etiketler:</strong> {tags_str}"

    # Tahmini okuma süresini ekle
    body_text += f"<br/><strong>Tahmini Okuma Suresi:</strong> {reading_time}"

    fe.description(body_text)

    # Tarih ve zaman bilgilerini ekleme
    if 'Published_Date_Formatted' in item and item['Published_Date_Formatted']:
        fe.description(f"{fe.description()}<br/><strong>Yayın Tarihi:</strong> {item['Published_Date_Formatted']}")
        try:
            fe.pubDate(item['Published_Date_Formatted'])
        except:
            pass

    if 'Published_Time' in item and item['Published_Time']:
        fe.description(f"{fe.description()}<br/><strong>Yayın Saati:</strong> {item['Published_Time']}")

    # GUID ekleme
    fe.guid(str(item['Link']))

@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request):
    """Render the home page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/airports/{iata_code}", response_class=HTMLResponse)
async def airport_detail(request: Request, iata_code: str):
    try:
        # Havalimanı verilerini al
        airport_data = airport_collection.find_one({"IATACode": iata_code.upper()})  # IATA kodunu büyük harfe çevir
        
        # Havalimanı bulunamadıysa 404 hatası döndür
        if not airport_data:
            raise HTTPException(
                status_code=404, 
                detail=f"'{iata_code}' IATA kodlu havalimanı bulunamadı"
            )
        
        # Haberleri al ve işle
        news_items = get_data_from_source(iata_code)
        
        # Haber tarihlerini işle
        for item in news_items:
            try:
                item['parsed_date'] = datetime.strptime(item['Published_Date_Formatted'], '%Y-%m-%d')
            except:
                item['parsed_date'] = datetime.min
        
        # Haberleri tarihe göre sırala
        news_items.sort(key=lambda x: x['parsed_date'], reverse=True)
        
        # Etiketleri düzenle
        if 'tagList' in airport_data:
            airport_data['tagList'] = airport_data['tagList'].replace('\\b', '').replace('\\b', '')
        
        # Template verilerini hazırla
        context = {
            "request": request,
            "iata_code": iata_code.upper(),
            "airport_name": airport_data.get('AirportName', 'Bilinmiyor'),
            "airport_city": airport_data.get('City', 'Bilinmiyor'),
            "airport_country": airport_data.get('CountryName', 'Bilinmiyor'),
            "airport_data": airport_data,
            "news_items": news_items,
            "rss_url": f"/rss/{iata_code}",
            "calculate_reading_time": calculate_reading_time
        }
        
        return templates.TemplateResponse("airport_detail.html", context)
    
    except HTTPException as he:
        # HTTP hatalarını yeniden yükselt
        raise he
    except Exception as e:
        print(f"Beklenmeyen hata oluştu: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Sunucu hatası: {str(e)}"
        )
