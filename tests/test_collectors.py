from unittest.mock import MagicMock, patch
import pytest
from app.collectors.rss import RSSCollector
from app.collectors.google_news import GoogleNewsCollector

# Mock feed XML content
MOCK_FEED_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Mock News Channel</title>
    <link>https://mocknews.com</link>
    <description>Mock Description</description>
    <item>
      <title>Sensex rises 500 points - Economic Times</title>
      <link>https://mocknews.com/articles/1</link>
      <description>&lt;p&gt;This is a &lt;b&gt;mock&lt;/b&gt; description text.&lt;/p&gt;</description>
      <pubDate>Sun, 23 Aug 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

@patch("app.collectors.rss.requests.get")
def test_rss_collector(mock_get):
    """Test standard RSS collection with HTML stripping."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = MOCK_FEED_XML.encode("utf-8")
    mock_get.return_value = mock_response
    
    config = {
        "name": "Test RSS Feed",
        "url": "https://mocknews.com/rss",
        "category": "MARKET",
        "country": "India",
        "enabled": True,
        "priority": 1
    }
    
    collector = RSSCollector(config)
    stories = collector.fetch()
    
    assert len(stories) == 1
    story = stories[0]
    assert story["title"] == "Sensex rises 500 points - Economic Times"
    assert story["article_url"] == "https://mocknews.com/articles/1"
    assert story["category"] == "MARKET"
    # Ensure BeautifulSoup stripped the <p> and <b> tags
    assert story["summary"] == "This is a mock description text."
    
@patch("app.collectors.rss.requests.get")
def test_google_news_collector(mock_get):
    """Test Google News RSS parsing which isolates publishers and trims headlines."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = MOCK_FEED_XML.encode("utf-8")
    mock_get.return_value = mock_response
    
    config = {
        "name": "Google News Test",
        "url": "https://news.google.com/rss",
        "category": "MARKET",
        "country": "India",
        "enabled": True,
        "priority": 1
    }
    
    collector = GoogleNewsCollector(config)
    stories = collector.fetch()
    
    assert len(stories) == 1
    story = stories[0]
    # Check Google News Title Split
    assert story["title"] == "Sensex rises 500 points"
    assert story["source_name"] == "Economic Times"
