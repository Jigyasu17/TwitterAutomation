import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base, Story, StorySource
from app.processing.normalize import normalize_url, clean_text
from app.processing.classifier import (
    classify_category, 
    identify_event_type, 
    extract_entities, 
    calculate_scores
)
from app.processing.deduplication import add_or_merge_story, find_duplicate_story

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

def test_url_normalization():
    """Verify that UTM parameters, trailing slashes, and fragments are correctly stripped from URLs."""
    raw_url_1 = "https://example.com/news/123/?utm_source=google&utm_medium=email#comments"
    normalized_1 = normalize_url(raw_url_1)
    assert normalized_1 == "https://example.com/news/123"

    raw_url_2 = "https://example.com/item?id=45&ref=xyz&utm_campaign=winter"
    normalized_2 = normalize_url(raw_url_2)
    assert normalized_2 == "https://example.com/item?id=45"

def test_clean_text():
    """Verify text cleansing and stopwords filtering."""
    raw_title = "Tata Motors to invest in EV cars!"
    cleaned_with_stopwords = clean_text(raw_title, remove_stopwords=True)
    cleaned_without_stopwords = clean_text(raw_title, remove_stopwords=False)
    
    assert "to" not in cleaned_with_stopwords.split()
    assert "in" not in cleaned_with_stopwords.split()
    assert "tata" in cleaned_with_stopwords
    assert "motors" in cleaned_with_stopwords
    assert "ev" in cleaned_with_stopwords
    
    assert "to" in cleaned_without_stopwords.split()

def test_classification_and_event_type():
    """Verify category classification and event action type mapping."""
    # Test IPO
    cat, tags = classify_category("Atomberg Files IPO Papers with SEBI", "Draft papers filed")
    assert cat == "IPO"
    assert "REGULATORY" in tags
    
    event_type = identify_event_type("Atomberg Files IPO Papers with SEBI")
    assert event_type == "IPO_FILING"

    # Test Funding
    cat, tags = classify_category("Startup Navi raises $300M in Series B", "Navi funding round details")
    assert cat == "FUNDING"
    assert "STARTUP" in tags
    
    event_type = identify_event_type("Startup Navi raises $300M in Series B")
    assert event_type == "FUNDING"

def test_entity_extraction():
    """Verify company, person, sector, and country entity isolation."""
    title = "Ambani says Jio plans EV car launch in India next month"
    summary = "Mukesh Ambani confirms new plant details"
    
    entities = extract_entities(title, summary)
    
    assert "Jio" in entities["Companies"]
    assert "Mukesh Ambani" in entities["People"] or "Ambani" in entities["People"]
    assert "United States" not in entities["Countries"]
    assert "India" in entities["Countries"]
    assert "EV" in entities["Sectors"]

def test_scoring_weights_and_range():
    """Verify scoring logic ranges and weight distributions."""
    title = "Tata Motors EV division raises $1 Billion at record valuation"
    summary = "EV startup funding round sets record high"
    
    imp, post, conf, final, breakdown = calculate_scores(title, summary, "Reuters", 1)
    
    # Assert score ranges
    assert 0 <= imp <= 100
    assert 0 <= post <= 100
    assert 0 <= conf <= 100
    assert 0 <= final <= 100
    
    # Verify exact weighted rank score logic
    expected_weighted = int((imp * 0.50) + (post * 0.35) + (conf * 0.15))
    assert final == expected_weighted

def test_no_merge_company_conflict(db_session):
    """Verify that Level 4 similarity merges are skipped if stories contain different company entities."""
    now = datetime.utcnow()
    
    story_data_tata = {
        "title": "Tata Motors reports record quarterly profit",
        "source_name": "Reuters",
        "source_url": "https://reuters.com",
        "article_url": "https://reuters.com/tata-profit",
        "published_at": now,
        "category": "BUSINESS",
        "summary": "Tata profit numbers"
    }
    
    story_data_reliance = {
        "title": "Reliance reports record quarterly profit",
        "source_name": "Economic Times",
        "source_url": "https://economictimes.com",
        "article_url": "https://economictimes.com/reliance-profit",
        "published_at": now,
        "category": "BUSINESS",
        "summary": "Reliance profit numbers"
    }
    
    # Insert Tata story
    story_tata = add_or_merge_story(db_session, story_data_tata, similarity_threshold=0.8)
    
    # Try inserting Reliance story (extremely similar title text except for company entity name)
    story_reliance = add_or_merge_story(db_session, story_data_reliance, similarity_threshold=0.8)
    
    # They MUST remain separate events!
    assert story_tata.id != story_reliance.id
    assert db_session.query(Story).count() == 2
