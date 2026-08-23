import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base, Story, StorySource
from app.processing.deduplication import (
    normalize_title,
    generate_content_hash,
    calculate_similarity,
    find_duplicate_story,
    add_or_merge_story
)

DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture
def db_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

def test_normalize_title():
    """Verify that titles are properly normalized by stripping punctuation and whitespaces."""
    assert normalize_title("Tata Motors raises ₹5,000 Cr; EV Expansion?") == "tata motors raises 5000 cr ev expansion"
    assert normalize_title("   Spaces   Everywhere   ") == "spaces everywhere"
    assert normalize_title("") == ""
    assert normalize_title(None) == ""

def test_similarity():
    """Verify that title similarity ratios are computed correctly."""
    title1 = "Tata Motors to invest 5000 crore in EV space"
    title2 = "Tata Motors plans 5,000 crore EV investment"
    score = calculate_similarity(title1, title2)
    assert score > 0.70  # Should be highly similar
    
    score_different = calculate_similarity(title1, "Sensex climbs 400 points")
    assert score_different < 0.40

def test_deduplication_levels(db_session):
    """Test Level 1, 2, and 3 deduplication flows."""
    now = datetime.utcnow()
    
    story_data_1 = {
        "title": "Startup XYZ raises 10 million dollars",
        "source_name": "TechCrunch",
        "source_url": "https://techcrunch.com",
        "article_url": "https://techcrunch.com/xyz-10m",
        "published_at": now,
        "category": "STARTUP",
        "country": "Global",
        "summary": "XYZ funding details"
    }
    
    # First insert
    story1 = add_or_merge_story(db_session, story_data_1)
    
    # Level 1: Duplicate URL
    story_data_dup_url = story_data_1.copy()
    story_data_dup_url["source_name"] = "VentureBeat"
    story_data_dup_url["title"] = "Different Title Same URL"
    
    story_dup_url = add_or_merge_story(db_session, story_data_dup_url)
    assert story_dup_url.id == story1.id
    
    # Level 2: Duplicate exact title hash (different URL)
    story_data_dup_hash = story_data_1.copy()
    story_data_dup_hash["article_url"] = "https://venturebeat.com/xyz-10m-round"
    story_data_dup_hash["source_name"] = "VentureBeat"
    
    story_dup_hash = add_or_merge_story(db_session, story_data_dup_hash)
    assert story_dup_hash.id == story1.id
    assert len(story1.sources) == 2  # TechCrunch and VentureBeat
    
    # Level 3: Title Similarity (paraphrased title, different URL)
    story_data_similarity = {
        "title": "Startup XYZ raised 10 million dollars",
        "source_name": "Economic Times",
        "source_url": "https://economictimes.com",
        "article_url": "https://economictimes.com/xyz-funding-news",
        "published_at": now,
        "category": "STARTUP",
        "country": "India"
    }
    
    story_similarity = add_or_merge_story(db_session, story_data_similarity)
    assert story_similarity.id == story1.id
    assert len(story1.sources) == 3  # TechCrunch, VentureBeat, and Economic Times
