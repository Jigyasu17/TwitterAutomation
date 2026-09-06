import hashlib
import logging
import difflib
from datetime import datetime
from typing import Optional, List, Any
from app.domain.models import StoryData, StorySourceData
from app.repositories.interfaces import StoryRepository
from app.processing.normalize import normalize_url, clean_text
from app.processing.classifier import extract_entities, identify_event_type

logger = logging.getLogger(__name__)

# Event types material enough that two differently-worded articles sharing
# one of these plus a common company are almost certainly the same
# underlying event (e.g. "Company X shares rise 8%" and "Company X profit
# jumps 42%" both being PROFIT_UPDATE for the same company on the same day).
# Deliberately excludes "OTHER" and low-signal types to avoid over-merging
# unrelated stories that happen to mention the same company.
CLUSTERABLE_EVENT_TYPES = {
    "FUNDING", "ACQUISITION", "MERGER", "IPO_FILING", "IPO_PRICING", "IPO_LISTING",
    "IPO_ANNOUNCEMENT", "EARNINGS", "PROFIT_UPDATE", "REVENUE_UPDATE",
    "STOCK_MOVEMENT", "REGULATORY_ACTION", "LAYOFF", "INVESTMENT", "EXPANSION",
    "POLICY_CHANGE",
}

# classifier.extract_entities() puts regulators into the same "Companies"
# bucket as actual listed companies (its KNOWN_COMPANIES dict includes
# "sebi"/"rbi" so a headline naming the regulator still gets tagged).
# SEBI/RBI approve or comment on nearly every regulatory/IPO story in this
# feed, so leaving them in the company-conflict/event-fingerprint checks
# below created a live false-positive merge: "NSE gets SEBI nod for its own
# Rs 30,000cr IPO" and "Jio Platforms gets SEBI clearance for its IPO" share
# only "sebi" as a "common company" and were wrongly clustered as one event.
# Unlike NSE/BSE (which sometimes genuinely ARE the story's subject, as in
# that NSE example), SEBI/RBI are never themselves the listed entity a
# MarketPulse story is about — they're always the regulator in the sentence,
# so they're excluded here specifically (not from extract_entities() itself,
# which drafts/builder.py's separate wire-service guard already handles for
# drafting purposes).
_PURE_REGULATOR_NAMES = {"sebi", "rbi"}


def _real_companies(entities: dict) -> set:
    return {c.lower() for c in entities.get("Companies", []) if c.lower() not in _PURE_REGULATOR_NAMES}

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

    companies1 = _real_companies(ent1)
    companies2 = _real_companies(ent2)
    
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

def _event_fingerprint_match(
    title: str, summary: str, published_at, candidate: StoryData, lookback_days: int
) -> bool:
    """
    Level 5: same underlying EVENT rather than similar wording. Catches cases
    like "Company X shares rise 8% after results" vs. "Company X profit jumps
    42%" — near-zero raw title-text overlap, but the same company + the same
    material event type within a short window is a reliable signal they're
    describing one event, not two.

    Requires a real company match (never merges on event_type alone) and a
    materially-clusterable event_type, so it can't accidentally fold two
    unrelated same-company stories (e.g. an earnings report and an unrelated
    executive appointment) into one.
    """
    event_type = identify_event_type(title)
    if event_type not in CLUSTERABLE_EVENT_TYPES:
        return False
    if identify_event_type(candidate.title) != event_type:
        return False

    incoming_companies = _real_companies(extract_entities(title, summary or ""))
    if not incoming_companies:
        return False

    candidate_entities = candidate.entities or {}
    candidate_companies = _real_companies(candidate_entities)
    if not candidate_companies:
        # Candidate hasn't been through classification yet (still NEW) — fall
        # back to extracting from its own title/summary directly.
        candidate_companies = _real_companies(extract_entities(candidate.title, candidate.summary or ""))
    if not incoming_companies.intersection(candidate_companies):
        return False

    if published_at and candidate.published_at:
        try:
            delta_seconds = abs((published_at - candidate.published_at).total_seconds())
            if delta_seconds > lookback_days * 86400:
                return False
        except Exception:
            pass

    return True


def find_duplicate_story(
    story_repo: StoryRepository,
    article_url: str,
    title: str,
    summary: str = "",
    similarity_threshold: float = 0.8,
    lookback_days: int = 7,
    published_at=None,
) -> Optional[StoryData]:
    """
    Checks if a story is a duplicate using 5 levels of matching:
    - Level 1 & 2: Exact or normalized article URL
    - Level 3: Exact content hash of normalized title
    - Level 4: Title similarity (SequenceMatcher) with company mismatch check
    - Level 5: Event fingerprint (same company + same material event type
      within a short window) — catches differently-worded coverage of the
      same underlying event that Level 4's text similarity misses.

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

    # Levels 4 & 5 share a single fetch of recent stories, ordered and
    # bounded by RECENCY (published_at), not by score — a score-ordered pool
    # silently drops every brand-new, not-yet-classified candidate (which
    # starts at final_score=0) once the database holds more already-scored
    # stories than the pool's limit, defeating both dedup levels for
    # same-day duplicates. See get_recent_stories_for_dedup() docstring.
    recent_stories = repo.get_recent_stories_for_dedup(lookback_days=lookback_days, limit=500)

    for story in recent_stories:
        # First check if companies conflict
        if has_company_conflict(title, summary, story.title, story.summary):
            continue

        score = calculate_similarity(title, story.title)
        if score >= similarity_threshold:
            logger.info(f"Duplicate Level 4 (Similarity: {score:.2f}) found: '{title}' matches '{story.title}'")
            return story

    for story in recent_stories:
        if has_company_conflict(title, summary, story.title, story.summary):
            continue
        if _event_fingerprint_match(title, summary, published_at, story, lookback_days):
            logger.info(f"Duplicate Level 5 (Event fingerprint) found: '{title}' clustered into event #{story.id} ('{story.title}')")
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

    pub_at = story_data["published_at"]
    if isinstance(pub_at, str):
        pub_at = datetime.fromisoformat(pub_at)

    # Check for duplicates using refined pipeline
    duplicate = find_duplicate_story(
        repo,
        clean_url,
        story_data["title"],
        story_data.get("summary", ""),
        similarity_threshold=similarity_threshold,
        published_at=pub_at,
    )
        
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

            # Promote the new article to be the PRIMARY representation if
            # its source is more authoritative than the current primary's —
            # e.g. a Reuters report of the same event as an already-saved
            # aggregator-sourced story should become the headline, not stay
            # buried as a mere confirming source. Only display fields move;
            # article_url/content_hash/id stay put — they're identity keys
            # (collection_job.py's new-vs-merged counting compares the
            # incoming item's URL against story.article_url, which would
            # break if promotion silently rewrote it).
            from app.processing.source_quality import get_source_tier
            if get_source_tier(story_data["source_name"]) < get_source_tier(duplicate.source_name):
                duplicate.title = story_data["title"]
                duplicate.source_name = story_data["source_name"]
                duplicate.source_url = story_data.get("source_url", duplicate.source_url)
                duplicate.summary = story_data.get("summary", duplicate.summary)
                duplicate.image_url = story_data.get("image_url", duplicate.image_url)
                logger.info(f"Promoted '{story_data['source_name']}' to primary representation for Story #{duplicate.id} (higher source tier)")

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
