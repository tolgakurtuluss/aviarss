import os
import datetime
import subprocess
import time
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
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
# MongoDB connection using environment variables
client = MongoClient(os.environ.get("MONGODB_URI"), server_api=ServerApi('1'))  # Get MongoDB URI from environment variable
db = client[os.environ.get("DATABASE_NAME")]  # Get database name from environment variable
collection = db[os.environ.get("COLLECTION_NAME")]  # Get collection name from environment variable
def get_data_from_source(iata_code=None):
    # Fetch documents from MongoDB
    if iata_code:
        # Load airport data from Excel
        airport_df = pd.read_excel("./data/airportcode.xlsx")
        airport_df = airport_df[airport_df['IATACode'] == iata_code]
        # Check if the airport_df is empty
        if airport_df.empty:
            return []  # Return an empty list if no matching IATA code is found
        # Get the tagList for the specified IATA code
        tag_list = airport_df['tagList'].values[0]  # Get the tagList as a string
        tags = tag_list.split(', ')  # Split the tagList into a list of tags

        # Create a query to filter documents based on the tags
        query = {'$or': [{'Body': {'$regex': tag, '$options': 'i'}} for tag in tags]}
        filtered_items = list(collection.find(query))
        # Add matched tags to each item
        for item in filtered_items:
            matched_tags = [tag for tag in tags if tag.lower() in item['Body'].lower()]
            item['matched_tags'] = matched_tags  # Add only matched tags to each item
        return filtered_items
    else:
        return []
    
def process_rss_feeds(rss_sources):
    # Initialize data storage
    data = {'Title': [], 'Body': [], 'Link': [], 'Published_Date': [], 'Published_Date_Formatted': [], 'Published_Time': []}
    # Parse RSS sources
    for source in rss_sources:
        feed = feedparser.parse(source)
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
    # Read existing records from MongoDB
    existing_records = collection.distinct("Link")  # Get unique links from existing records
    # Filter out existing records
    df['is_existing'] = df['Link'].isin(existing_records)
    new_records = df[~df['is_existing']].drop(columns=['is_existing'])
    # Upload new unique records to MongoDB
    records = new_records.to_dict(orient='records')
    if records:
        collection.insert_many(records)
        print(f"Successfully uploaded {len(records)} new records to MongoDB.")
    else:
        print("No new records found to upload.")
# Example list of RSS sources
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
def run_feed_update_if_time():
    now = datetime.datetime.now()
        
    if 30 <= now.minute <= 35:
        # Call the function with the RSS sources
        process_rss_feeds(rss_sources)
        print("feedupdate.py has been executed.")
        
@app.get("/rss/{iata_code}")
def generate_rss_feed(iata_code: str):
    fg = FeedGenerator()
    fg.title(f'{iata_code} RSS Feed')
    fg.link(href='http://www.example.com', rel='alternate')
    fg.description('This is an example RSS feed')
    # Run feed update in a background task
    run_feed_update_if_time()
    items = get_data_from_source(iata_code)
    if not items:  # Check if the list is empty
        raise HTTPException(status_code=404, detail="No items found for the given IATA code")
    for item in items:
        fe = fg.add_entry()
        fe.title(str(item['Title']))
        # Get the body text
        body_text = str(item['Body'])
        # Include only matched tags in the description
        if 'matched_tags' in item and item['matched_tags']:
            # Bold the matched tags in the body text
            for tag in item['matched_tags']:
                # Use regex to replace the tag with a bolded version
                body_text = body_text.replace(tag, f"<strong><u>{tag}</u></strong>")
        # Set the modified body text as the description
        fe.description(body_text)
        # Append matched tags to the description
        if 'matched_tags' in item and item['matched_tags']:
            tags_str = ', '.join(item['matched_tags'])  # Convert matched tags list to a string
            fe.description(f"{fe.description()}<hr/><br/><br/><strong>Matched Tags:</strong> {tags_str}")
        # Include published date and time if available
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
