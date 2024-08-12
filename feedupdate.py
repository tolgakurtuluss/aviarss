import os
import feedparser
import pandas as pd
from bs4 import BeautifulSoup
from dateutil import parser
from pymongo import MongoClient
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi


client = MongoClient(os.environ.get("MONGODB_URI"), server_api=ServerApi('1'))
db = client[os.environ.get("DATABASE_NAME")] 
collection = db[os.environ.get("COLLECTION_NAME")]

def parse_rss_sources(rss_sources):
    data = {'Title': [], 'Body': [], 'Link': [], 'Published_Date': [], 'Published_Date_Formatted': [], 'Published_Time': []}

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
    return df

def filter_new_records(df, existing_records):
    # Filter out records that already exist in MongoDB
    df['is_existing'] = df['Link'].isin(existing_records)
    new_records = df[~df['is_existing']].drop(columns=['is_existing'])
    return new_records

# Function to upload new unique records to MongoDB
def upload_new_records_to_mongodb(df):
    # Convert DataFrame to dictionary format for MongoDB
    records = df.to_dict(orient='records')

    # Insert records into MongoDB
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

# Read existing records from MongoDB
existing_records = collection.distinct("Link")  # Get unique links from existing records

# Parse the RSS sources and store in a data frame
df = parse_rss_sources(rss_sources)

# Filter out existing records
new_records_df = filter_new_records(df, existing_records)

# Call the upload function for new unique records
upload_new_records_to_mongodb(new_records_df)