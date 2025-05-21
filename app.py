import os
import pandas as pd
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
        # Fetch airport data from MongoDB
        airport_data = airport_collection.find_one({"IATACode": iata_code})
        if not airport_data:
            return pd.DataFrame()
        
        # Convert MongoDB data to DataFrame
        df = pd.DataFrame([{
            'IATACode': airport_data['IATACode'],
            'AirportName': airport_data['AirportName'],
            'City': airport_data['City'],
            'Country': airport_data['CountryName'],
            'tagList': airport_data.get('tagList', '')
        }])
        return df
    except Exception as e:
        print(f"Error fetching airport data: {e}")
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
    fg.title(f'{iata_code} Airport RSS Feed')
    fg.link(href=f'https://aviarss.onrender.com/rss/{iata_code}', rel='self')
    fg.link(href='https://aviarss.onrender.com', rel='alternate')
    fg.description(f'News and updates related to {iata_code} airport')
    fg.language('en')
    fg.lastBuildDate()
    fg.generator('AviRSS Feed Generator')

    items = get_data_from_source(iata_code)

    if not items:
        raise HTTPException(status_code=404, detail="No items found for the specified IATA code")

    for item in items:
        add_item_to_feed(fg, item)

    rss_feed = fg.rss_str(pretty=True)
    
    return Response(content=rss_feed, media_type='application/rss+xml')

AVERAGE_READING_SPEED_WPM = 185

def calculate_reading_time(text):
    """
    Calculates the estimated time required to read the text.
    Average reading speed: 185 words/minute
    Output format: X minutes Y seconds
    """
    words = len(text.split())
    total_minutes = words / AVERAGE_READING_SPEED_WPM
    
    # Calculate full minutes and seconds
    minutes = int(total_minutes)
    seconds = int((total_minutes - minutes) * 60)
    
    if minutes == 0 and seconds < 30:
        return "Less than 30 seconds"
    elif minutes == 0:
        return f"{seconds} seconds"
    elif seconds == 0:
        return f"{minutes} minutes"
    else:
        return f"{minutes} min {seconds} sec"

def add_item_to_feed(fg, item):
    """Add a single item to the RSS feed."""
    fe = fg.add_entry()
    fe.title(str(item['Title']))
    fe.link(href=str(item['Link']))
    
    # Add author information
    if 'Author' in item and item['Author']:
        fe.author({'name': item['Author']})
    else:
        fe.author({'name': 'AviRSS'})

    body_text = str(item['Body'])

    # Calculate estimated reading time
    reading_time = calculate_reading_time(item['Title'] + " " + body_text)
    
    if 'matched_tags' in item and item['matched_tags']:
        for tag in item['matched_tags']:
            body_text = body_text.replace(tag, f"<strong><u>{tag}</u></strong>")
        tags_str = ', '.join(item['matched_tags'])
        body_text += f"<hr/><br/><br/><strong>Matched Tags:</strong> {tags_str}"

    # Add estimated reading time
    body_text += f"<br/><strong>Estimated Reading Time:</strong> {reading_time}"

    fe.description(body_text)

    # Add date and time information
    if 'Published_Date_Formatted' in item and item['Published_Date_Formatted']:
        fe.description(f"{fe.description()}<br/><strong>Published Date:</strong> {item['Published_Date_Formatted']}")
        try:
            fe.pubDate(item['Published_Date_Formatted'])
        except:
            pass # Could not parse date

    if 'Published_Time' in item and item['Published_Time']:
        fe.description(f"{fe.description()}<br/><strong>Published Time:</strong> {item['Published_Time']}")

    # Add GUID
    fe.guid(str(item['Link']))

@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request):
    """Render the home page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/airports/{iata_code}", response_class=HTMLResponse)
async def airport_detail(request: Request, iata_code: str):
    try:
        # Fetch airport data
        airport_data = airport_collection.find_one({"IATACode": iata_code.upper()})  # Convert IATA code to uppercase
        
        # If airport not found, return 404 error
        if not airport_data:
            raise HTTPException(
                status_code=404, 
                detail=f"Airport with IATA code '{iata_code}' not found"
            )
        
        # Get and process news
        news_items = get_data_from_source(iata_code)
        
        # Process news dates for sorting
        for item in news_items:
            try:
                item['parsed_date'] = datetime.strptime(item['Published_Date_Formatted'], '%Y-%m-%d')
            except:
                item['parsed_date'] = datetime.min # Default to a very old date if parsing fails
        
        # Sort news by date in descending order
        news_items.sort(key=lambda x: x['parsed_date'], reverse=True)
        
        # Clean up tagList if it exists - this was present in the original code
        if 'tagList' in airport_data:
            airport_data['tagList'] = airport_data['tagList'].replace('\\b', '').replace('\\b', '')
        
        # Prepare template data
        context = {
            "request": request,
            "iata_code": iata_code.upper(),
            "airport_name": airport_data.get('AirportName', 'Unknown'),
            "airport_city": airport_data.get('City', 'Unknown'),
            "airport_country": airport_data.get('CountryName', 'Unknown'),
            "airport_data": airport_data,
            "news_items": news_items,
            "rss_url": f"/rss/{iata_code}",
            "calculate_reading_time": calculate_reading_time  # Pass the function itself
        }
        
        return templates.TemplateResponse("airport_detail.html", context)
    
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        print(f"Unexpected error occurred: {str(e)}") # Log unexpected errors
        raise HTTPException(
            status_code=500, 
            detail=f"Server error: {str(e)}"
        )
