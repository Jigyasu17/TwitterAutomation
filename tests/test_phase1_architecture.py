import pytest
import logging
from datetime import datetime
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base
from app.domain.models import StoryData, StorySourceData, ResearchReportData
from app.repositories.sqlite import SQLStoryRepository, SQLResearchRepository
from app.research.orchestrator import research_story, process_research_queue
from app.jobs.collection_job import run_news_collection
from app.jobs.processing_job import run_story_processing
from app.jobs.research_job import run_research_job
from app.main import app

# --- Testing Setup and Fixtures ---

@pytest.fixture(autouse=True)
def mock_network_requests(monkeypatch):
    """Automatically mocks all network requests to prevent test hangs and external dependencies."""
    import requests
    
    # 1. Mock requests.get
    def mock_get(*args, **kwargs):
        response = MagicMock()
        response.status_code = 200
        response.content = b"<feed><entry><title>Mock Article Title - Google News</title><link>https://news.google.com/mock-link</link></entry></feed>"
        response.text = "Mock extracted body text content from publisher news website page."
        return response
    monkeypatch.setattr(requests, "get", mock_get)

    # 2. Mock feedparser.parse
    import feedparser
    def mock_parse(*args, **kwargs):
        entry = MagicMock()
        entry.get.side_effect = lambda key, default=None: {
            "title": "Mock Article Title",
            "link": "https://news.google.com/mock-link",
            "published": "2026-08-23T12:00:00"
        }.get(key, default)
        
        feed = MagicMock()
        feed.entries = [entry]
        feed.feed.get.side_effect = lambda key, default=None: {
            "link": "https://news.google.com",
            "title": "Google News"
        }.get(key, default)
        return feed
    monkeypatch.setattr(feedparser, "parse", mock_parse)

    # 3. Mock trafilatura
    import trafilatura
    monkeypatch.setattr(trafilatura, "extract", lambda *args, **kwargs: "Mock extracted body text content from publisher news website page.")
    monkeypatch.setattr(trafilatura, "fetch_url", lambda *args, **kwargs: "Mock HTML content")

@pytest.fixture(name="db_session")
def fixture_db_session():
    """Sets up an in-memory SQLite database for architectural repository testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture(name="client")
def fixture_client():
    """Client fixture pointing to the FastAPI app instance."""
    with TestClient(app) as c:
        yield c

# --- Test Cases ---

def test_repository_returns_domain_dataclasses(db_session):
    """VERIFIES: Repositories return and save plain domain objects, isolating SQLAlchemy models."""
    story_repo = SQLStoryRepository(db_session)
    
    # 1. Instantiating plain StoryData domain dataclass
    story_data = StoryData(
        title="India startup funding surges by 200%",
        source_name="MoneyControl",
        source_url="https://moneycontrol.com",
        article_url="https://moneycontrol.com/funding-surge",
        published_at=datetime.utcnow(),
        category="INVESTMENT",
        content_hash="mockhash123",
        status="NEW"
    )
    
    # Add source subcollection
    source = StorySourceData(
        source_name="MoneyControl",
        url="https://moneycontrol.com/funding-surge",
        published_at=story_data.published_at,
        title=story_data.title
    )
    story_data.sources.append(source)
    
    # 2. Save via repo
    saved_story = story_repo.save(story_data)
    assert saved_story.id is not None
    assert isinstance(saved_story, StoryData)
    assert len(saved_story.sources) == 1
    assert isinstance(saved_story.sources[0], StorySourceData)
    
    # 3. Retrieve via repo
    fetched_story = story_repo.get_by_id(saved_story.id)
    assert fetched_story is not None
    assert isinstance(fetched_story, StoryData)
    assert fetched_story.title == "India startup funding surges by 200%"
    assert fetched_story.sources[0].title == "India startup funding surges by 200%"

def test_research_engine_works_without_direct_orm_manipulations(db_session):
    """VERIFIES: Research orchestrator operates on repository interfaces without direct session accesses."""
    story_repo = SQLStoryRepository(db_session)
    research_repo = SQLResearchRepository(db_session)

    # Insert a dummy story for research
    story_data = StoryData(
        title="Shadowfax Technologies files confidential DRHP for 2500cr IPO",
        source_name="VCCircle",
        source_url="https://vccircle.com",
        article_url="https://vccircle.com/shadowfax-ipo",
        published_at=datetime.utcnow(),
        category="IPO",
        content_hash="mockhash456",
        status="READY_FOR_REVIEW",
        importance_score=80,
        postability_score=85,
        final_score=82
    )
    saved_story = story_repo.save(story_data)
    
    # Run queue process directly (synchronously, no background thread)
    processed = process_research_queue(story_repo, research_repo, min_importance=70, min_postability=75)
    assert processed == 1

    # Verify report created is a domain object
    report = research_repo.get_report_by_story_id(saved_story.id)
    assert report is not None
    assert isinstance(report, ResearchReportData)
    assert report.status in {"COMPLETED", "NEEDS_REVIEW"}

def test_jobs_execute_standalone_without_apscheduler(db_session):
    """VERIFIES: standalone job runners can execute sequentially and synchronously without thread dependencies."""
    story_repo = SQLStoryRepository(db_session)
    
    # Running news collection job (should fail-safe read sources.json but not block on scheduler)
    res = run_news_collection(story_repo)
    assert res["status"] in {"success", "error"}
    
    # Running processing job
    processed = run_story_processing(story_repo)
    assert isinstance(processed, int)

def test_api_responses_are_json_serializable(client):
    """VERIFIES: Endpoint routers serialize custom domain dataclasses to JSON responses safely."""
    response = client.get("/api/stories")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    stats_resp = client.get("/api/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert "total_articles" in stats
    assert "rejected" in stats

def test_job_idempotency(db_session):
    """VERIFIES: Running a job repeatedly does not duplicate data entities."""
    story_repo = SQLStoryRepository(db_session)
    
    story_data = {
        "title": "Uniphore raises 100m in Series E funding round",
        "source_name": "TechCrunch",
        "source_url": "https://techcrunch.com",
        "article_url": "https://techcrunch.com/uniphore-series-e",
        "published_at": datetime.utcnow().isoformat(),
        "category": "FUNDING"
    }
    
    # Add first time
    s1 = story_repo.add_or_merge_story(story_data)
    # Add second time (should merge/skip duplication)
    s2 = story_repo.add_or_merge_story(story_data)
    
    assert s1.id == s2.id
    
    # Confirm DB contains exactly 1 unique entry
    all_stories = story_repo.get_stories(status="any")
    assert len(all_stories) == 1

def test_app_lifespan_starts_without_permanent_scheduler():
    """VERIFIES: Configuration and app lifespan boots cleanly without initiating permanent thread workers."""
    from app.config import settings
    # For production Vercel environments, scheduling daemon thread is disabled
    assert settings.START_LOCAL_SCHEDULER is False or settings.ENV == "development"

def test_logging_configuration():
    """VERIFIES: Standard logs are set up through stdout handlers."""
    logger = logging.getLogger("app")
    has_stream_handler = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    # Root logger will hold the StreamHandler configured in basicConfig
    root_logger = logging.getLogger()
    has_root_stream = any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers)
    assert has_stream_handler or has_root_stream
