from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseCollector(ABC):
    def __init__(self, source_config: Dict[str, Any]):
        """
        Initializes the collector.
        
        Args:
            source_config: Dictionary containing source settings:
                - name: Name of the source
                - url: Feed or query URL
                - category: Default category (e.g. MARKET, STOCK, etc.)
                - country: Country of origin (e.g. India, Global)
                - priority: Priority score (1-3)
        """
        self.source_config = source_config
        self.name = source_config.get("name")
        self.url = source_config.get("url")
        self.category = source_config.get("category", "GENERAL")
        self.country = source_config.get("country", "Global")
        self.priority = source_config.get("priority", 3)

    @abstractmethod
    def fetch(self) -> List[Dict[str, Any]]:
        """
        Fetches raw content from the source and parses it.
        
        Returns:
            List of parsed stories in dict format:
            {
                "title": str,
                "article_url": str,
                "source_name": str,
                "source_url": str,
                "published_at": datetime,
                "category": str,
                "country": str,
                "summary": Optional[str],
                "raw_content": Optional[str],
                "image_url": Optional[str]
            }
        """
        pass
