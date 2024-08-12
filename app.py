import os
import datetime
import subprocess
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from feedgen.feed import FeedGenerator
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import pandas as pd
from pymongo import MongoClient
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# MongoDB connection using environment variables
client = MongoClient(os.environ.get("MONGODB_URI"), server_api=ServerApi('1'))  # Get MongoDB URI from environment variable
db = client[os.environ.get("DATABASE_NAME")]  # Get database name from environment variable
collection = db[os.environ.get("COLLECTION_NAME")]  # Get collection name from environment variable

def get_data_from_source(iata_code = None):
    # Fetch documents from MongoDB
    if iata_code:
        # Assuming you have a way to get the tags from the IATA code
        airportdf = pd.read_excel("./data/airportcode.xlsx")
        airportdf = airportdf[airportdf['IATACode'] == iata_code]

        airportdf['tags'] = airportdf[['IATACode', 'AirportName', 'CountryName', 'City']].values.tolist()
        tags = [tag for sublist in airportdf['tags'] for tag in sublist]

        # Create a query to filter documents based on the tags
        query = {'$or': [{'Body': {'$regex': tag, '$options': 'i'}} for tag in tags]}
        filtered_items = list(collection.find(query))

        return filtered_items
    else:
        # If no IATA code is provided, return all items
        return []

def run_feed_update_if_time():
    while True:
        now = datetime.datetime.now()
        
        # Check if the current minute is between 30 and 35
        if 30 <= now.minute <= 35:
            # Construct the path to the feedupdate.py script
            script_path = os.path.join(os.path.dirname(__file__), 'feedupdate.py')
            
            # Run the script
            subprocess.run(['python', script_path], check=True)
            print("feedupdate.py has been executed.")
        
@app.get("/rss/{iata_code}")
def generate_rss_feed(iata_code: str):
    fg = FeedGenerator()
    fg.title(f'{iata_code} RSS Feed')
    fg.link(href='http://www.example.com', rel='alternate')
    fg.description('This is an example RSS feed')

    run_feed_update_if_time()

    items = get_data_from_source(iata_code)

    if items.empty:
        raise HTTPException(status_code=404, detail="No items found for the given IATA code")

    for index, item in items.iterrows():
        fe = fg.add_entry()
        fe.title(str(item['Title']))
        fe.description(str(item['Body']))
        fe.link(href=str(item['Link']))

    rss_feed = fg.rss_str(pretty=True)
    return Response(content=rss_feed, media_type='application/rss+xml')

@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
