import logging
from typing import List, Dict, Any
from app.collectors.rss import RSSCollector

logger = logging.getLogger(__name__)

class GoogleNewsCollector(RSSCollector):
    def fetch(self) -> List[Dict[str, Any]]:
        """
        Fetches Google News RSS feeds and refines the story attributes by 
        extracting the original publisher name from the end of the title.
        """
        stories = super().fetch()
        
        for story in stories:
            title = story["title"]
            
            # Google News headlines typically end with " - Publisher Name"
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                cleaned_title = parts[0].strip()
                extracted_source = parts[1].strip()
                
                if cleaned_title and extracted_source and len(extracted_source) < 50:
                    story["title"] = cleaned_title
                    story["source_name"] = extracted_source
                    
        return stories
