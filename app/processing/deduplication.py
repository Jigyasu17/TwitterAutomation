import hashlib
import logging
import difflib
from datetime import datetime
from typing import Optional, List, Any
from app.domain.models import StoryData, StorySourceData
from app.repositories.interfaces import StoryRepository
from app.processing.normalize import normalize_url, clean_text
from app.processing.classifier import extract_entities

logger = logging.getLogger(__name__)

def normalize_title(title: str) -> str:
    """Legacy compatibility wrapper for Milestone 1 tests."""
    return clean_text(title, remove_stopwords=False)

def generate_content_hash(text: str) -> str:
    """Generates an MD5 hash of the given normalized, stopwords-filtered text."""
    normalized = clean_text(text, remove_stopwords=True)
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()

def calculate_similarity(title1: str, title2: str) -> float:
    """
    Calculates similarity between two titles using Python's built-in SequenceMatcher.
    Comparison is done on cleaned, normalized text to reduce formatting differences.
    """
    norm1 = clean_text(title1, remove_stopwords=False)
    norm2 = clean_text(title2, remove_stopwords=False)
    return difflib.SequenceMatcher(None, norm1, norm2).ratio()

def has_company_conflict(title1: str, summary1: str, title2: str, summary2: str) -> bool:
    """
    Determines if two stories refer to different companies.
    If both stories have extracted companies and they do not share any common company,
    we consider it a conflict (they must not be merged).
    """
    ent1 = extract_entities(title1, summary1 or "")
    ent2 = extract_entities(title2, summary2 or "")
    
    companies1 = {c.lower() for c in ent1.get("Companies", [])}
    companies2 = {c.lower() for c in ent2.get("Companies", [])}
    
    # If both stories identify at least one company, and their sets have zero overlap
    if companies1 and companies2 and not companies1.intersection(companies2):
        logger.debug(f"Company Conflict Detected: {companies1} vs {companies2}. Skipping merge.")
        return True
        
    return False

def _ensure_repository(story_repo: Any) -> StoryRepository:
    """Compatibility wrapper checking if a Session was passed, converting it to SQLStoryRepository."""
    if not hasattr(story_repo, "get_by_url"):
        # We got a raw SQLAlchemy Session instead of a Repository adapter! (e.g. from old tests)
        from app.repositories.sqlite.story_repository import SQLStoryRepository
        return SQLStoryRepository(story_repo)
    return story_repo

def find_duplicate_story(
    story_repo: StoryRepository, 
    article_url: str, 
    title: str, 
    summary: str = "",
    similarity_threshold: float = 0.8, 
    lookback_days: int = 7
) -> Optional[StoryData]:
    """
    Checks if a story is a duplicate using 4 levels of matching:
    - Level 1 & 2: Exact or normalized article URL
    - Level 3: Exact content hash of normalized title
    - Level 4: Title similarity (SequenceMatcher) with company mismatch check
    
    Returns the duplicate StoryData if found, else None.
    """
    repo = _ensure_repository(story_repo)

    # Level 1 & 2: Clean input URL (UTMs removed) and match directly
    clean_url = normalize_url(article_url)
    url_match = repo.get_by_url(clean_url)
    if url_match:
        logger.debug(f"Duplicate Level 1/2 (URL) found: {clean_url}")
        return url_match

    # Level 3: Exact title hash match
    title_hash = generate_content_hash(title)
    hash_match = repo.get_by_hash(title_hash)
    if hash_match:
        logger.debug(f"Duplicate Level 3 (Hash) found: {title}")
        return hash_match

    # Level 4: Title similarity comparison lookback
    # Fetches recent stories from repository (last 150 items)
    recent_stories = repo.get_stories(status="any", limit=150)
    
    for story in recent_stories:
        # First check if companies conflict
        if has_company_conflict(title, summary, story.title, story.summary):
            continue
            
        score = calculate_similarity(title, story.title)
        if score >= similarity_threshold:
            logger.info(f"Duplicate Level 4 (Similarity: {score:.2f}) found: '{title}' matches '{story.title}'")
            return story

    return None

def add_or_merge_story(story_repo: StoryRepository, story_data: dict, similarity_threshold: float = 0.8) -> StoryData:
    """
    Adds a story or merges it with an existing one if a duplicate is found.
    Normalizes the article URL and increments confidence score if merged.
    """
    repo = _ensure_repository(story_repo)

    raw_url = story_data["article_url"]
    clean_url = normalize_url(raw_url)
    
    # Check for duplicates using refined pipeline
    duplicate = find_duplicate_story(
        repo, 
        clean_url, 
        story_data["title"], 
        story_data.get("summary", ""),
        similarity_threshold=similarity_threshold
    )
    
    pub_at = story_data["published_at"]
    if isinstance(pub_at, str):
        pub_at = datetime.fromisoformat(pub_at)
        
    if duplicate:
        # Check if source is already added
        source_exists = any(src.url == raw_url for src in duplicate.sources)
        
        if not source_exists:
            new_source = StorySourceData(
                story_id=duplicate.id,
                source_name=story_data["source_name"],
                url=raw_url,
                published_at=pub_at or datetime.utcnow(),
                title=story_data["title"]
            )
            duplicate.sources.append(new_source)
            repo.save(duplicate)
            logger.info(f"Merged duplicate article '{story_data['title']}' into Story #{duplicate.id}")
            
        return duplicate

    # Create new story with normalized URL
    content_hash = generate_content_hash(story_data["title"])
    
    new_story = StoryData(
        title=story_data["title"],
        source_name=story_data["source_name"],
        source_url=story_data["source_url"],
        article_url=clean_url,
        published_at=pub_at or datetime.utcnow(),
        category=story_data["category"],
        country=story_data.get("country", "Global"),
        summary=story_data.get("summary"),
        image_url=story_data.get("image_url"),
        content_hash=content_hash,
        status="NEW",
        sources=[]
    )
    
    # Add initial source list
    initial_source = StorySourceData(
        source_name=new_story.source_name,
        url=raw_url,
        published_at=new_story.published_at,
        title=new_story.title
    )
    new_story.sources.append(initial_source)
    
    saved_story = repo.save(new_story)
    return saved_story
