import json
import logging
from pathlib import Path
from app.repositories.interfaces import StoryRepository
from app.collectors.rss import RSSCollector
from app.collectors.google_news import GoogleNewsCollector
from app.processing.normalize import normalize_url

logger = logging.getLogger(__name__)

def run_news_collection(story_repo: StoryRepository) -> dict:
    """
    Executes the RSS/Google News collection process.
    Operates strictly via StoryRepository boundaries.
    """
    sources_path = Path(__file__).resolve().parent.parent / "collectors" / "sources.json"
    if not sources_path.exists():
        logger.error(f"Sources registry not found at: {sources_path}")
        return {"status": "error", "message": "Sources registry configuration not found."}
        
    try:
        with open(sources_path, "r", encoding="utf-8") as f:
            sources = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read sources registry: {e}")
        return {"status": "error", "message": "Failed to load sources configuration."}
        
    total_fetched = 0
    new_stories_count = 0
    failed_sources = []
    
    for src in sources:
        if not src.get("enabled", True):
            continue
            
        collector_type = src.get("type", "rss")
        try:
            if collector_type == "google_news":
                collector = GoogleNewsCollector(src)
            else:
                collector = RSSCollector(src)
                
            fetched_items = collector.fetch()
            total_fetched += len(fetched_items)
            
            for item in fetched_items:
                story = story_repo.add_or_merge_story(item)
                # Check if it was a newly created story or a merged duplicate.
                # story.article_url is always the normalized URL, so the raw feed
                # URL must be normalized the same way before comparing, otherwise
                # every new story with a tracking param gets miscounted as merged.
                if story.article_url == normalize_url(item["article_url"]):
                    new_stories_count += 1
        except Exception as e:
            logger.error(f"Error collecting from source '{src.get('name')}': {e}")
            failed_sources.append(src.get("name"))
            
    logger.info(f"News collection run completed. Total: {total_fetched}, New: {new_stories_count}, Merged: {total_fetched - new_stories_count}")
    return {
        "status": "success",
        "total_fetched": total_fetched,
        "new_stories": new_stories_count,
        "merged_stories": total_fetched - new_stories_count,
        "failed_sources": failed_sources
    }
