# AviARSS: Airport RSS Feeds

AviARSS is a Python-based web application that provides airport-specific RSS feeds and web pages. It fetches news and updates related to airports using their IATA codes and makes them available through a web interface and RSS feeds.

The application uses FastAPI for the web framework, Jinja2 for templating, and MongoDB as the database to store airport information and news articles.

## Features

- Display airport details (name, city, country) based on IATA code.
- Show a list of news articles related to a specific airport.
- Generate an RSS feed for news articles of a specific airport.
- Automatic updates of news articles from various sources via a scheduled GitHub Actions workflow that runs the `update_mongodb.py` script.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    Make sure you have Python 3.8 or higher installed.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    The application requires the following environment variables for MongoDB connection:
    - `MONGODB_URI`: Your MongoDB connection string.
    - `DATABASE_NAME`: The name of your database.
    - `COLLECTION_NAME`: The name of the collection for news articles.
    - `AIRPORT_COLLECTION_NAME`: The name of the collection for airport data.

    You can set these in your environment or create a `.env` file (though be sure not to commit it if it contains sensitive credentials).

5.  **Run the application:**
    ```bash
    uvicorn app:app --reload
    ```
    The application will be accessible at `http://127.0.0.1:8000`.

## Usage

### Web Interface

-   **Home Page:** `http://127.0.0.1:8000/`
    - Displays a general landing page.
-   **Airport Detail Page:** `http://127.0.0.1:8000/airports/{iata_code}`
    - Example: `http://127.0.0.1:8000/airports/IST`
    - Shows details for the specified airport and lists related news articles.
-   **RSS Feed:** `http://127.0.0.1:8000/rss/{iata_code}`
    - Example: `http://127.0.0.1:8000/rss/IST`
    - Provides an RSS feed of news articles for the specified airport.

### Automatic Data Updates

The news articles and airport data in MongoDB are updated automatically every 30 minutes by a GitHub Actions workflow (`.github/workflows/update_mongodb.yml`). This workflow executes the `update_mongodb.py` script.

## Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request.
(You can add more specific contribution guidelines if needed)

## License

(Specify a license if you have one, e.g., MIT License. If not, you can state "This project is unlicensed.")
