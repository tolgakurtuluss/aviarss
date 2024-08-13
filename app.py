import os
import datetime
import asyncio
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from feedgen.feed import FeedGenerator
import feedparser
import pandas as pd
from bs4 import BeautifulSoup
from dateutil import parser
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Validate and set environment variables
mongo_uri = os.environ.get("MONGODB_URI")
database_name = os.environ.get("DATABASE_NAME")
collection_name = os.environ.get("COLLECTION_NAME")

if not mongo_uri or not database_name or not collection_name:
    raise ValueError("MongoDB configuration is not set correctly.")

# MongoDB connection using environment variables
client = MongoClient(mongo_uri, server_api=ServerApi('1'))
db = client[database_name]
collection = db[collection_name]

def calculate_similarity(text, tags, threshold=0.9):
    vectorizer = TfidfVectorizer().fit_transform([text] + tags)
    vectors = vectorizer.toarray()
    cosine_sim = cosine_similarity(vectors[0:1], vectors[1:])
    matched = [tags[i] for i in range(len(tags)) if cosine_sim[0][i] > threshold]
    logger.info(f"Matched tags for text: {text} are {matched}")
    return matched

    
async def get_data_from_source(iata_code=None):
    if iata_code:
        # Load airport data from Excel
        airport_df = pd.read_excel("./data/airportcode.xlsx")
        airport_df = airport_df[airport_df['IATACode'] == iata_code]

        if airport_df.empty:
            return []  # Return an empty list if no matching IATA code is found

        tag_list = airport_df['tagList'].values[0]  # Get the tagList as a string
        tags = tag_list.split(', ')  # Split the tagList into a list of tags

        query = {'$or': [{'Body': {'$regex': tag, '$options': 'i'}} for tag in tags]}
        filtered_items = list(collection.find(query))

        for item in filtered_items:
            matched_tags = calculate_similarity(item['Body'], tags)
            item['matched_tags'] = matched_tags
            logger.info(f"Item: {item['Body']} matched tags: {matched_tags}")

    else:
        return []

async def parse_feed(source):
    try:
        feed = feedparser.parse(source)
        data = {'Title': [], 'Body': [], 'Link': [], 'Published_Date': [], 'Published_Date_Formatted': [], 'Published_Time': []}

        for entry in feed.entries:
            data['Title'].append(entry.title)
            soup = BeautifulSoup(entry.summary, 'html.parser')
            text = soup.get_text().strip()
            data['Body'].append(text)
            data['Link'].append(entry.link)
            
            if 'published' in entry:
                data['Published_Date'].append(entry.published)
                try:
                    parsed_date = parser.parse(entry.published)
                    data['Published_Date_Formatted'].append(parsed_date.strftime('%Y-%m-%d'))
                    data['Published_Time'].append(parsed_date.strftime('%H:%M:%S'))
                except ValueError:
                    data['Published_Date_Formatted'].append(None)
                    data['Published_Time'].append(None)
            else:
                data['Published_Date'].append(None)
                data['Published_Date_Formatted'].append(None)
                data['Published_Time'].append(None)

        df = pd.DataFrame(data)
        existing_records = collection.distinct("Link")
        df['is_existing'] = df['Link'].isin(existing_records)
        new_records = df[~df['is_existing']].drop(columns=['is_existing'])

        records = new_records.to_dict(orient='records')
        if records:
            collection.insert_many(records)
            logger.info("Successfully uploaded %d new records to MongoDB.", len(records))
        else:
            logger.info("No new records found to upload.")
    except Exception as e:
        logger.error("Failed to parse RSS feed: %s", source)
        logger.error("Error details: %s", str(e))

async def process_rss_feeds(rss_sources):
    tasks = [asyncio.create_task(parse_feed(source)) for source in rss_sources]
    await asyncio.gather(*tasks)

rss_sources = [
    'https://www.airporthaber2.com/rss/',
    'https://haber.aero/feed/',
    'https://havasosyalmedya.com/feed/', 
    'https://www.airlinehaber.com/feed/',
    'https://www.aeroroutes.com/?format=rss',
    'https://tolgaozbek.com/feed/',
    'https://airlinegeeks.com/feed/',
    'https://www.flyertalk.com/feed',
    'https://worldairlinenews.com/feed/',
    'https://www.flightradar24.com/blog/feed/',
    'https://www.sabre.com/feed/',
    'https://www.cirium.com/thoughtcloud/feed/',
    'https://www.aerotime.aero/category/airlines/feed',
    'https://www.radarbox.com/blog/feed',
    'https://simpleflying.com/feed/',
    'https://theaviationist.com/feed/',
    'https://feeds.feedburner.com/Ex-yuAviationNews',
    'https://samchui.com/feed/'
]

@app.get("/rss/{iata_code}")
async def generate_rss_feed(iata_code: str):
    fg = FeedGenerator()
    fg.title(f'{iata_code} RSS Feed')
    fg.link(href='http://www.example.com', rel='alternate')
    fg.description('This is an example RSS feed')

    now = datetime.datetime.now()
    if 30 <= now.minute <= 35:
        await process_rss_feeds(rss_sources)

    items = await get_data_from_source(iata_code)

    if not items:
        raise HTTPException(status_code=404, detail="No items found for the given IATA code")

    for item in items:
        fe = fg.add_entry()
        fe.title(str(item['Title']))
        body_text = str(item['Body'])
    
        if 'matched_tags' in item and item['matched_tags']:
            for tag in item['matched_tags']:
                body_text = body_text.replace(tag, f"<strong><u>{tag}</u></strong>")
    
            tags_str = ', '.join(item['matched_tags'])
            body_text += f"<br/><br/><strong>Matched Tags:</strong> {tags_str}"
    
        fe.description(body_text)
    
        if 'Published_Date_Formatted' in item and item['Published_Date_Formatted']:
            fe.description(f"{fe.description()}<br/><strong>Published Date:</strong> {item['Published_Date_Formatted']}")
    
        if 'Published_Time' in item and item['Published_Time']:
            fe.description(f"{fe.description()}<br/><strong>Published Time:</strong> {item['Published_Time']}")
    
        fe.link(href=str(item['Link']))

    rss_feed = fg.rss_str(pretty=True)
    return Response(content=rss_feed, media_type='application/rss+xml')

@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
