import logging
import urllib.parse
import feedparser
import requests
from datetime import datetime
from typing import List
from app.domain.models import StoryData, ResearchSourceData
from app.processing.classifier import SOURCE_PRIORITIES, clean_and_lower
from app.processing.deduplication import calculate_similarity

logger = logging.getLogger(__name__)

def discover_sources(story: StoryData) -> List[ResearchSourceData]:
    """
    Discovers research sources for a given story.
    1. Reuses existing story_sources from deduplicated mergers.
    2. Searches Google News RSS for the primary company + category to find additional links.
    """
    discovered_sources = []
    seen_urls = set()

    # --- Phase 1: Pool existing merged sources from DB ---
    if story.sources:
        for src in story.sources:
            norm_url = src.url.strip()
            if norm_url not in seen_urls:
                seen_urls.add(norm_url)
                
                # Determine source priority score
                priority = 60
                source_key = clean_and_lower(src.source_name)
                for key, val in SOURCE_PRIORITIES.items():
                    if key in source_key:
                        priority = val
                        break
                        
                discovered_sources.append(ResearchSourceData(
                    source_name=src.source_name,
                    title=src.title,
                    url=src.url,
                    published_date=src.published_at,
                    source_type="google_news" if "news.google" in src.url else "rss",
                    priority=priority
                ))
                
    # --- Phase 2: Dynamic discovery using Google News search queries ---
    query_terms = []
    if story.company:
        query_terms.append(story.company)
    if story.category and story.category != "OTHER":
        query_terms.append(story.category)
        
    # If we don't have a company name, extract first three words of title as query
    if not query_terms:
        words = story.title.split()
        query_terms.extend(words[:3])
        
    query_str = " ".join(query_terms)
    encoded_query = urllib.parse.quote_plus(query_str)
    search_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    logger.info(f"Discovering additional sources with search query: '{query_str}'")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, http://127.0.0.1:8000/ and generic browsers)"
        }
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            feed = feedparser.parse(response.content)
            
            for entry in feed.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                
                if not title or not link:
                    continue
                    
                # Format publisher name and title
                extracted_source = "Google News"
                cleaned_title = title
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    cleaned_title = parts[0].strip()
                    extracted_source = parts[1].strip()
                
                # Check for Jaccard/SequenceMatcher similarity with primary title to ensure relevance
                similarity = calculate_similarity(story.title, cleaned_title)
                if similarity >= 0.50:
                    norm_url = link.strip()
                    if norm_url not in seen_urls:
                        seen_urls.add(norm_url)
                        
                        priority = 60
                        source_key = clean_and_lower(extracted_source)
                        for key, val in SOURCE_PRIORITIES.items():
                            if key in source_key:
                                priority = val
                                break
                                
                        discovered_sources.append(ResearchSourceData(
                            source_name=extracted_source,
                            title=cleaned_title,
                            url=link,
                            source_type="google_news",
                            priority=priority
                        ))
                        
                        # Limit extra discovered sources to top 3 to prevent over-scraping
                        if len(discovered_sources) >= 6:
                            break
                            
    except Exception as e:
        logger.error(f"Error during dynamic source discovery: {e}")
        
    return discovered_sources
