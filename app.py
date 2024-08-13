import os
import datetime
import pandas as pd
import feedparser
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup
from dateutil import parser
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# Initialize FastAPI app and templates
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# MongoDB connection using environment variables
mongo_client = MongoClient(os.environ.get("MONGODB_URI"), server_api=ServerApi('1'))
db = mongo_client[os.environ.get("DATABASE_NAME")]
collection = db[os.environ.get("COLLECTION_NAME")]
rss_sources_collection = db[os.environ.get("RSS_SOURCES_COLLECTION_NAME")]
airport_collection = db[os.environ.get("AIRPORT_COLLECTION_NAME")]

# Fetch RSS sources from MongoDB
rss_sources = [doc['rss_source'] for doc in rss_sources_collection.find({}, {'rss_source': 1})]

all_documents = list(airport_collection.find())
airport_df = pd.DataFrame(all_documents)

def fetch_airport_data(iata_code):
    """Fetch airport data from Excel based on IATA code."""
    return airport_df[airport_df['IATACode'] == iata_code]

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

def process_rss_feeds(rss_sources):
    """Process RSS feeds and upload new records to MongoDB."""
    data = {
        'Title': [],
        'Body': [],
        'Link': [],
        'Published_Date': [],
        'Published_Date_Formatted': [],
        'Published_Time': []
    }

    for source in rss_sources:
        feed = feedparser.parse(source)
        for entry in feed.entries:
            data['Title'].append(entry.title)
            data['Body'].append(BeautifulSoup(entry.summary, 'html.parser').get_text().strip())
            data['Link'].append(entry.link)
            process_entry_date(entry, data)

    df = pd.DataFrame(data)
    upload_new_records_to_mongo(df)

def process_entry_date(entry, data):
    """Process the published date of an RSS entry."""
    if 'published' in entry:
        try:
            parsed_date = parser.parse(entry.published)
            data['Published_Date'].append(entry.published)
            data['Published_Date_Formatted'].append(parsed_date.strftime('%Y-%m-%d'))
            data['Published_Time'].append(parsed_date.strftime('%H:%M:%S'))
        except ValueError:
            data['Published_Date'].append(None)
            data['Published_Date_Formatted'].append(None)
            data['Published_Time'].append(None)
    else:
        data['Published_Date'].append(None)
        data['Published_Date_Formatted'].append(None)
        data['Published_Time'].append(None)

def upload_new_records_to_mongo(df):
    """Upload new unique records to MongoDB."""
    existing_records = collection.distinct("Link")
    df['is_existing'] = df['Link'].isin(existing_records)
    new_records = df[~df['is_existing']].drop(columns=['is_existing'])

    records = new_records.to_dict(orient='records')
    if records:
        collection.insert_many(records)
        print(f"Successfully uploaded {len(records)} new records to MongoDB.")
    else:
        print("No new records found to upload.")

def run_feed_update_if_time():
    """Run feed update if the current time is within the specified range."""
    now = datetime.datetime.now()
    if 30 <= now.minute <= 35:
        process_rss_feeds(rss_sources)
        print("feedupdate.py has been executed.")

@app.get("/rss/{iata_code}")
def generate_rss_feed(iata_code: str):
    """Generate RSS feed for the given IATA code."""
    fg = FeedGenerator()
    fg.title(f'{iata_code} RSS Feed')
    fg.link(href='http://www.example.com', rel='alternate')
    fg.description('This is an example RSS feed')

    run_feed_update_if_time()
    items = get_data_from_source(iata_code)

    if not items:
        raise HTTPException(status_code=404, detail="No items found for the given IATA code")

    for item in items:
        add_item_to_feed(fg, item)

    rss_feed = fg.rss_str(pretty=True)
    return Response(content=rss_feed, media_type='application/rss+xml')

def add_item_to_feed(fg, item):
    """Add a single item to the RSS feed."""
    fe = fg.add_entry()
    fe.title(str(item['Title']))
    body_text = str(item['Body'])

    if 'matched_tags' in item and item['matched_tags']:
        for tag in item['matched_tags']:
            body_text = body_text.replace(tag, f"<strong><u>{tag}</u></strong>")
        tags_str = ', '.join(item['matched_tags'])
        body_text += f"<hr/><br/><br/><strong>Matched Tags:</strong> {tags_str}"

    fe.description(body_text)

    if 'Published_Date_Formatted' in item and item['Published_Date_Formatted']:
        fe.description(f"{fe.description()}<br/><strong>Published Date:</strong> {item['Published_Date_Formatted']}")

    if 'Published_Time' in item and item['Published_Time']:
        fe.description(f"{fe.description()}<br/><strong>Published Time:</strong> {item['Published_Time']}")

    fe.link(href=str(item['Link']))

@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request):
    """Render the home page."""
    return templates.TemplateResponse("index.html", {"request": request})
