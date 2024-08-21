import os
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from feedgen.feed import FeedGenerator
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
airport_collection = db[os.environ.get("AIRPORT_COLLECTION_NAME")]

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

@app.get("/rss/{iata_code}")
def generate_rss_feed(iata_code: str):
    """Generate RSS feed for the given IATA code."""
    fg = FeedGenerator()
    fg.title(f'{iata_code} RSS Feed')
    fg.link(href='http://www.example.com', rel='alternate')
    fg.description('This is an example RSS feed')

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
