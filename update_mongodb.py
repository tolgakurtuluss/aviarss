import os
import pandas as pd
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# MongoDB connection using environment variables
mongo_client = MongoClient(os.environ.get("MONGODB_URI"), server_api=ServerApi('1'))
db = mongo_client[os.environ.get("DATABASE_NAME")]
collection = db[os.environ.get("COLLECTION_NAME")]
rss_sources_collection = db[os.environ.get("RSS_SOURCES_COLLECTION_NAME")]

# Fetch RSS sources from MongoDB
rss_sources = [doc['rss_source'] for doc in rss_sources_collection.find({}, {'rss_source': 1})]

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

if __name__ == '__main__':
    # Read existing records from MongoDB
    existing_records = collection.distinct("Link")  # Get unique links from existing records
    
    # Parse the RSS sources and store in a data frame
    df = parse_rss_sources(rss_sources)
    
    # Filter out existing records
    new_records_df = filter_new_records(df, existing_records)
    
    # Call the upload function for new unique records
    upload_new_records_to_mongodb(new_records_df)
