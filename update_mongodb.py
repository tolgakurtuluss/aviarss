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
# This retrieves a list of RSS feed URLs from the 'rss_sources_collection'.
rss_sources = [doc['rss_source'] for doc in rss_sources_collection.find({}, {'rss_source': 1})]

def parse_rss_sources(rss_sources):
    """
    Parses a list of RSS feed URLs and extracts relevant data into a pandas DataFrame.
    For each entry in each feed, it extracts the title, body (cleaned HTML), link,
    and publication date/time.
    """
    data = {'Title': [], 'Body': [], 'Link': [], 'Published_Date': [], 'Published_Date_Formatted': [], 'Published_Time': []}

    for source_url in rss_sources:
        feed = feedparser.parse(source_url)
        for entry in feed.entries:
            data['Title'].append(entry.title)
            
            # Parse HTML from summary and extract text
            soup = BeautifulSoup(entry.summary, 'html.parser')
            text = soup.get_text().strip()
            data['Body'].append(text)
            data['Link'].append(entry.link)
            
            # Handle publication date parsing
            if 'published' in entry:
                data['Published_Date'].append(entry.published)
                try:
                    # Attempt to parse the date string
                    parsed_date = parser.parse(entry.published)
                    data['Published_Date_Formatted'].append(parsed_date.strftime('%Y-%m-%d'))
                    data['Published_Time'].append(parsed_date.strftime('%H:%M:%S'))
                except ValueError:
                    # If date parsing fails, store None for formatted date and time
                    data['Published_Date_Formatted'].append(None)
                    data['Published_Time'].append(None)
            else:
                # If no 'published' field, store None
                data['Published_Date'].append(None)
                data['Published_Date_Formatted'].append(None)
                data['Published_Time'].append(None)

    df = pd.DataFrame(data)
    return df

def filter_new_records(df, existing_links):
    """
    Filters out records from the DataFrame that already exist in MongoDB,
    based on their 'Link'.
    'existing_links' is a list of links already present in the database.
    """
    # Check if each link in the DataFrame is already in the list of existing links
    df['is_existing'] = df['Link'].isin(existing_links)
    # Select only records that are not existing and drop the temporary 'is_existing' column
    new_records = df[~df['is_existing']].drop(columns=['is_existing'])
    return new_records

def upload_new_records_to_mongodb(df):
    """
    Uploads new, unique records from the DataFrame to MongoDB.
    """
    # Convert DataFrame to a list of dictionaries, as expected by insert_many
    records = df.to_dict(orient='records')

    if records:
        collection.insert_many(records)
        print(f"Successfully uploaded {len(records)} new records to MongoDB.")
    else:
        print("No new records found to upload.")

if __name__ == '__main__':
    # Fetch unique 'Link' values from all existing records in the MongoDB collection.
    # This is used to avoid inserting duplicate news items.
    print("Fetching existing record links from MongoDB...")
    existing_record_links = collection.distinct("Link")
    print(f"Found {len(existing_record_links)} existing links.")
    
    # Parse the RSS sources and store new items in a DataFrame
    print(f"Parsing {len(rss_sources)} RSS source(s)...")
    df_all_items = parse_rss_sources(rss_sources)
    print(f"Parsed {len(df_all_items)} items from all sources.")
    
    # Filter out records that already exist in the database
    print("Filtering out existing records...")
    new_records_df = filter_new_records(df_all_items, existing_record_links)
    print(f"Found {len(new_records_df)} new records to potentially upload.")
    
    # Upload the new, unique records to MongoDB
    upload_new_records_to_mongodb(new_records_df)
    print("MongoDB update process finished.")
