import logging
from datetime import datetime
import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from typing import List, Dict, Any
from app.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

class RSSCollector(BaseCollector):
    def fetch(self) -> List[Dict[str, Any]]:
        stories = []
        try:
            logger.info(f"Fetching RSS feed: {self.name} from {self.url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            # Fetch content with timeout
            response = requests.get(self.url, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.error(f"Failed to fetch {self.name}: HTTP {response.status_code}")
                return []
            
            feed = feedparser.parse(response.content)
            source_url = feed.feed.get("link", self.url)
            
            for entry in feed.entries:
                title = entry.get("title")
                link = entry.get("link")
                
                if not title or not link:
                    continue
                
                # Parse publish date
                published_at = None
                pub_date_parsed = entry.get("published_parsed")
                if pub_date_parsed:
                    published_at = datetime(*pub_date_parsed[:6])
                else:
                    pub_str = entry.get("published") or entry.get("updated")
                    if pub_str:
                        try:
                            published_at = date_parser.parse(pub_str)
                            # Convert to timezone-naive UTC datetime for standard database storage
                            if published_at.tzinfo is not None:
                                published_at = published_at.astimezone().replace(tzinfo=None)
                        except Exception:
                            published_at = datetime.utcnow()
                    else:
                        published_at = datetime.utcnow()
                
                # Clean HTML tags from summary description
                summary_raw = entry.get("summary") or entry.get("description", "")
                summary = ""
                if summary_raw:
                    try:
                        soup = BeautifulSoup(summary_raw, "html.parser")
                        summary = soup.get_text().strip()
                    except Exception:
                        summary = summary_raw
                
                # Attempt image URL extraction
                image_url = None
                media_content = entry.get("media_content")
                if media_content and isinstance(media_content, list) and len(media_content) > 0:
                    image_url = media_content[0].get("url")
                
                if not image_url:
                    media_thumbnail = entry.get("media_thumbnail")
                    if media_thumbnail and isinstance(media_thumbnail, list) and len(media_thumbnail) > 0:
                        image_url = media_thumbnail[0].get("url")
                
                stories.append({
                    "title": title,
                    "article_url": link,
                    "source_name": self.name,
                    "source_url": source_url,
                    "published_at": published_at,
                    "category": self.category,
                    "country": self.country,
                    "summary": summary if summary else None,
                    "raw_content": summary_raw if summary_raw else None,
                    "image_url": image_url
                })
                
        except Exception as e:
            logger.error(f"Error fetching RSS feed {self.name}: {e}", exc_info=True)
            
        return stories
