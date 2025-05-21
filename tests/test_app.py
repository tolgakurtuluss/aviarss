import unittest
import pandas as pd
from fastapi import HTTPException
from app import calculate_reading_time, generate_rss_feed, app # Assuming app.py is in the root
from unittest.mock import patch, MagicMock

class TestApp(unittest.TestCase):

    def test_calculate_reading_time(self):
        self.assertEqual(calculate_reading_time("word " * 10), "Less than 30 seconds")
        self.assertEqual(calculate_reading_time("word " * 30), "Less than 30 seconds") # Approx 0.16 min
        self.assertEqual(calculate_reading_time("word " * 90), "29 seconds") # Approx 0.48 min
        self.assertEqual(calculate_reading_time("word " * 185), "1 minutes") # 1 min
        self.assertEqual(calculate_reading_time("word " * 277), "1 min 30 sec") # 1.5 min
        self.assertEqual(calculate_reading_time("word " * 370), "2 minutes") # 2 min
        self.assertEqual(calculate_reading_time(""), "Less than 30 seconds") # Empty string

    @patch('app.get_data_from_source')
    def test_generate_rss_feed_success(self, mock_get_data):
        # Mock the data source to return a predefined list of items
        mock_item = {
            'Title': 'Test Title',
            'Link': 'http://example.com/test',
            'Body': 'Test body content.',
            'Author': 'Test Author',
            'Published_Date_Formatted': '2023-01-01',
            'Published_Time': '12:00:00',
            'matched_tags': ['test', 'pytest']
        }
        mock_get_data.return_value = [mock_item]

        # Call the function
        response = generate_rss_feed(iata_code="TEST")
        content = response.body.decode(response.charset)

        # Basic checks for RSS structure and content
        self.assertIn("<rss version=\"2.0\">", content)
        self.assertIn("<channel>", content)
        self.assertIn("<title>TEST Airport RSS Feed</title>", content)
        self.assertIn("<link>https://aviarss.onrender.com/rss/TEST</link>", content)
        self.assertIn("<description>News and updates related to TEST airport</description>", content)
        self.assertIn("<language>en</language>", content)
        
        self.assertIn("<item>", content)
        self.assertIn("<title>Test Title</title>", content)
        self.assertIn("<link>http://example.com/test</link>", content)
        self.assertIn("<description>", content)
        self.assertIn("Test body content.", content)
        self.assertIn("<strong><u>test</u></strong>", content) # Check for tag highlighting
        self.assertIn("<strong><u>pytest</u></strong>", content)
        self.assertIn("Matched Tags:</strong> test, pytest", content)
        self.assertIn("Estimated Reading Time:", content)
        self.assertIn("Published Date:</strong> 2023-01-01", content)
        self.assertIn("Published Time:</strong> 12:00:00", content)
        self.assertIn("<guid>http://example.com/test</guid>", content)
        self.assertIn("<author>Test Author</author>", content) # Check author

    @patch('app.get_data_from_source')
    def test_generate_rss_feed_no_items(self, mock_get_data):
        # Mock the data source to return an empty list
        mock_get_data.return_value = []

        with self.assertRaises(HTTPException) as context:
            generate_rss_feed(iata_code="EMPTY")
        
        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(context.exception.detail, "No items found for the specified IATA code")

    # It might be useful to add a simple test for the FastAPI app instance if needed,
    # but that often requires a test client. For now, focusing on direct function calls.

if __name__ == '__main__':
    unittest.main()
