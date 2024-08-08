from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from feedgen.feed import FeedGenerator
import pandas as pd

app = FastAPI()

# Sample data retrieval function with IATA code filtering
def get_data_from_source(source, iata_code=None):
    if source == "excel":
        # Make sure to provide the correct path to your Excel file
        items = pd.read_excel("./data/rssdf.xlsx")

        airportdf = pd.read_excel("./data/airportcode.xlsx")
        airportdf = airportdf[airportdf['IATACode'] == iata_code]

        airportdf['tags'] = airportdf[['IATACode', 'AirportName', 'CountryName', 'City']].values.tolist()
        tags = [tag for sublist in airportdf['tags'] for tag in sublist]
        mask = items['Body'].apply(lambda body: any(tag in body for tag in tags) if pd.notna(body) else False)
        filtered_items = items[mask]

        return filtered_items        
        
    
def get_data_from_source2():
    items = pd.read_excel("./data/rssdf.xlsx")
    return items

@app.get("/rss/{iata_code}")
def generate_rss_feed(iata_code: str, source: str = "excel"):
    fg = FeedGenerator()
    fg.title(f'{iata_code} RSS Feed')
    fg.link(href='http://www.example.com', rel='alternate')
    fg.description('This is an example RSS feed')

    items = get_data_from_source(source, iata_code)

    if items.empty:
        raise HTTPException(status_code=404, detail="No items found for the given IATA code")

    for index, item in items.iterrows():
        fe = fg.add_entry()
        fe.title(str(item['Title']))
        fe.description(str(item['Body']))
        fe.link(href=str(item['Link']))

    rss_feed = fg.rss_str(pretty=True)
    return Response(content=rss_feed, media_type='application/rss+xml')

@app.get("/rss")
def generate_rss_feed2(source: str = "excel"):
    fg = FeedGenerator()
    fg.title('My RSS Feed')
    fg.link(href='http://www.example.com', rel='alternate')
    fg.description('This is an example RSS feed')

    items = get_data_from_source2()

    if items.empty:
        raise HTTPException(status_code=404, detail="No items found for the given IATA code")

    for index, item in items.iterrows():
        fe = fg.add_entry()
        fe.title(str(item['Title']))
        fe.description(str(item['Body']))
        fe.link(href=str(item['Link']))

    rss_feed = fg.rss_str(pretty=True)
    return Response(content=rss_feed, media_type='application/rss+xml')