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
