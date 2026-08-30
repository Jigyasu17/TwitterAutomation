import pytest
import datetime
from unittest.mock import MagicMock
from app.domain.models import StoryData, StorySourceData, ResearchReportData
from app.repositories.firestore.story_repository import (
    FirestoreStoryRepository,
    normalize_timestamp,
    map_story_domain_to_dict,
    map_story_dict_to_domain
)
from app.repositories.firestore.research_repository import (
    FirestoreResearchRepository,
    map_report_domain_to_dict,
    map_report_dict_to_domain
)
from tests.test_repository_contracts import MockFirestoreClient

# --- Timestamp Conversion Unit Tests ---

def test_timestamp_normalization():
    # 1. Normalizing timezone-naive datetime
    dt_naive = datetime.datetime(2026, 8, 23, 12, 0, 0)
    dt_normalized = normalize_timestamp(dt_naive)
    assert dt_normalized.tzinfo == datetime.timezone.utc
    assert dt_normalized.hour == 12

    # 2. Normalizing ISO-8601 string representation
    iso_str = "2026-08-23T15:30:00Z"
    dt_iso = normalize_timestamp(iso_str)
    assert dt_iso.tzinfo == datetime.timezone.utc
    assert dt_iso.minute == 30

    # 3. Handle None value
    assert normalize_timestamp(None) is None

# --- Serialization Unit Tests ---

def test_story_serialization():
    story = StoryData(
        title="PhonePe launches App Store",
        source_name="VentureBeat",
        source_url="https://venturebeat.com",
        article_url="https://venturebeat.com/phonepe",
        published_at=datetime.datetime(2026, 8, 23, 10, 0, 0, tzinfo=datetime.timezone.utc),
        category="STARTUP",
        content_hash="phonepe_hash",
        status="NEW",
        final_score=80
    )
    story.sources.append(StorySourceData(
        source_name="VentureBeat",
        url="https://venturebeat.com/phonepe",
        published_at=story.published_at,
        title=story.title
    ))

    # To Dict
    serialized = map_story_domain_to_dict(story)
    assert serialized["title"] == "PhonePe launches App Store"
    assert serialized["published_at"].tzinfo == datetime.timezone.utc
    assert len(serialized["sources"]) == 1
    assert serialized["sources"][0]["url"] == "https://venturebeat.com/phonepe"

    # From Dict
    deserialized = map_story_dict_to_domain("mock_doc_id", serialized)
    assert deserialized.id == "mock_doc_id"
    assert deserialized.title == "PhonePe launches App Store"
    assert len(deserialized.sources) == 1
    assert deserialized.sources[0].url == "https://venturebeat.com/phonepe"

# --- Research Queue Query Translation Unit Tests ---

def test_research_queue_criteria_filtering():
    mock_client = MockFirestoreClient()
    story_repo = FirestoreStoryRepository(client=mock_client)

    # Insert three stories:
    # 1. Eligible (high score, status NEW, no report)
    s1 = StoryData(
        id="story_1", 
        title="Story One", 
        status="NEW", 
        final_score=90, 
        importance_score=85, 
        postability_score=85,
        source_name="VentureBeat",
        source_url="https://venturebeat.com",
        article_url="https://venturebeat.com/s1",
        published_at=datetime.datetime.now(datetime.timezone.utc),
        category="STARTUP",
        content_hash="hash_s1"
    )
    story_repo.save(s1)
    
    # 2. Ineligible status (REJECTED)
    s2 = StoryData(
        id="story_2", 
        title="Story Two", 
        status="REJECTED", 
        final_score=95, 
        importance_score=90, 
        postability_score=90,
        source_name="VentureBeat",
        source_url="https://venturebeat.com",
        article_url="https://venturebeat.com/s2",
        published_at=datetime.datetime.now(datetime.timezone.utc),
        category="STARTUP",
        content_hash="hash_s2"
    )
    story_repo.save(s2)
    
    # 3. Low scores
    s3 = StoryData(
        id="story_3", 
        title="Story Three", 
        status="NEW", 
        final_score=30, 
        importance_score=20, 
        postability_score=25,
        source_name="VentureBeat",
        source_url="https://venturebeat.com",
        article_url="https://venturebeat.com/s3",
        published_at=datetime.datetime.now(datetime.timezone.utc),
        category="STARTUP",
        content_hash="hash_s3"
    )
    story_repo.save(s3)

    eligible_queue = story_repo.get_research_eligible_queue(min_importance=70, min_postability=75, limit=5)
    assert len(eligible_queue) == 1
    assert eligible_queue[0].id == "story_1"

# --- get_stories() In-Memory Category/Priority Filtering Unit Tests ---

def _make_story(id, status, category, final_score, source_name="VentureBeat"):
    return StoryData(
        id=id,
        title=f"Title {id}",
        status=status,
        category=category,
        final_score=final_score,
        source_name=source_name,
        source_url="https://venturebeat.com",
        article_url=f"https://venturebeat.com/{id}",
        published_at=datetime.datetime.now(datetime.timezone.utc),
        content_hash=f"hash_{id}"
    )

def test_get_stories_applies_category_and_priority_in_memory():
    """
    get_stories() only filters/sorts on `status` at the Firestore query level now
    (to keep the required composite index set fixed); category and priority are
    applied afterwards on the fetched page. Verify that still produces correct
    results, not just a query that runs without a FailedPrecondition.
    """
    mock_client = MockFirestoreClient()
    story_repo = FirestoreStoryRepository(client=mock_client)

    s1 = _make_story("s1", status="NEW", category="STARTUP", final_score=90)
    s2 = _make_story("s2", status="REJECTED", category="STARTUP", final_score=95)  # excluded by status="all"
    s3 = _make_story("s3", status="NEW", category="MARKET", final_score=50)  # excluded by category filter
    s4 = _make_story("s4", status="APPROVED", category="STARTUP", final_score=60)
    for s in (s1, s2, s3, s4):
        story_repo.save(s)

    # Category filter combined with the default "all" status filter
    startup_stories = story_repo.get_stories(status="all", category="STARTUP")
    assert {s.id for s in startup_stories} == {"s1", "s4"}

    # Priority filter (final_score >= 75) combined with default "all" status filter
    high_priority = story_repo.get_stories(status="all", priority="high")
    assert {s.id for s in high_priority} == {"s1"}

    # status="any" bypasses the status filter entirely (used internally by dedup)
    # so the REJECTED story must be included too
    any_status = story_repo.get_stories(status="any")
    assert {s.id for s in any_status} == {"s1", "s2", "s3", "s4"}

    # Pagination applies after in-memory filtering, on the filtered set
    page = story_repo.get_stories(status="all", category="STARTUP", limit=1, offset=1)
    assert [s.id for s in page] == ["s4"]


# --- Failure Exception Handling Unit Tests ---

def test_firestore_failure_handling():
    # Configure mock client that throws database errors during operations
    mock_client = MagicMock()
    mock_client.collection.side_effect = Exception("Connection timed out to google API gateway")
    
    story_repo = FirestoreStoryRepository(client=mock_client)
    research_repo = FirestoreResearchRepository(client=mock_client)

    # Verify story query failures raise controlled RuntimeErrors instead of crashing with SDK internal stack traces
    with pytest.raises(RuntimeError) as excinfo:
        story_repo.get_by_id("story_error_test")
    assert "Database error" in str(excinfo.value)

    with pytest.raises(RuntimeError) as excinfo_url:
        story_repo.get_by_url("https://error.com")
    assert "Database error" in str(excinfo_url.value)

    # Verify report query failures raise controlled RuntimeErrors
    with pytest.raises(RuntimeError) as excinfo_rep:
        research_repo.get_report_by_id("report_error_test")
    assert "Database error" in str(excinfo_rep.value)
