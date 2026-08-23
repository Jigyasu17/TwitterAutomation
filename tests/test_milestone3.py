import pytest
import json
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base, Story, ResearchReport, ResearchSource, ResearchFact, ResearchConflict
from app.database.repositories import SQLStoryRepository, SQLResearchRepository
from app.research.models import SourceDetails, Fact, ConflictAlert
from app.research.fact_normalizer import parse_monetary_value, normalize_percentage
from app.research.fact_extractor import extract_facts_from_text
from app.research.verifier import verify_facts
from app.research.scorer import calculate_research_confidence
from app.research.report_builder import build_research_report
from app.research.orchestrator import research_story, process_research_queue

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

def test_fact_normalization():
    """Verify that financial values and percentages are normalized correctly across USD/INR formats."""
    # Test Millions
    v, c = parse_monetary_value("$100 million")
    assert v == 100_000_000.0
    assert c == "USD"

    # Test Billions
    v, c = parse_monetary_value("USD 1.5 Billion")
    assert v == 1_500_000_000.0
    assert c == "USD"

    # Test Crores
    v, c = parse_monetary_value("₹5,000 crore")
    assert v == 50_000_000_000.0
    assert c == "INR"

    # Test Cr suffix
    v, c = parse_monetary_value("Rs 500 Cr")
    assert v == 5_000_000_000.0
    assert c == "INR"

    # Test Lakhs
    v, c = parse_monetary_value("10 Lakh rupees")
    assert v == 1_000_000.0
    assert c == "INR"

    # Test Percentage normalization
    assert normalize_percentage("12.5%") == 12.5
    assert normalize_percentage("-5.2 percent") == 5.2

def test_fact_extractor_rules():
    """Verify fact extraction patterns for funding, valuations, movements, and subscription numbers."""
    text = (
        "Tata Motors raises $1 Billion in its latest Series B funding round. "
        "The corporate valuation jumped to $10 Billion. "
        "Meanwhile, its stock price recorded a positive 5.5% jump. "
        "The IPO public issue was subscribed 12.5 times on closing day."
    )
    facts = extract_facts_from_text(text, source_id=1)
    
    types = {f.fact_type: f for f in facts}
    
    assert "funding_amount" in types
    assert types["funding_amount"].normalized_value == 1_000_000_000.0
    assert types["funding_amount"].currency == "USD"

    assert "valuation" in types
    assert types["valuation"].normalized_value == 10_000_000_000.0

    assert "stock_movement" in types
    assert types["stock_movement"].normalized_value == 5.5
    assert types["stock_movement"].unit == "percentage"

    assert "subscription_number" in types
    assert types["subscription_number"].normalized_value == 12.5
    assert types["subscription_number"].unit == "times"

def test_verifier_consensus_and_conflicts():
    """Verify agreement raises confidence, and mismatches trigger ConflictAlerts."""
    sources_map = {
        1: SourceDetails(source_name="Reuters", title="A", url="url_a", id=1),
        2: SourceDetails(source_name="ET", title="B", url="url_b", id=2)
    }

    # Case A: Consensus agreement (within 5% range)
    facts_agree = [
        Fact(fact_type="funding_amount", original_value="$100M", normalized_value=100_000_000.0, currency="USD", source_id=1),
        Fact(fact_type="funding_amount", original_value="$101M", normalized_value=101_000_000.0, currency="USD", source_id=2)
    ]
    verified, conflicts = verify_facts(facts_agree, sources_map)
    assert len(conflicts) == 0
    assert len(verified) == 1
    assert verified[0].confidence == 1.0  # Consensus boost

    # Case B: Conflict discrepancy (> 5% difference)
    facts_conflict = [
        Fact(fact_type="funding_amount", original_value="$100M", normalized_value=100_000_000.0, currency="USD", source_id=1),
        Fact(fact_type="funding_amount", original_value="$120M", normalized_value=120_000_000.0, currency="USD", source_id=2)
    ]
    verified, conflicts = verify_facts(facts_conflict, sources_map)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "VALUE_MISMATCH"
    assert conflicts[0].severity == "HIGH"
    assert conflicts[0].source_a == "Reuters"
    assert conflicts[0].source_b == "ET"

def test_confidence_scorer():
    """Verify scorer calculations based on primary sources, source diversity, and conflicts."""
    sources = [
        SourceDetails(source_name="Reuters", title="A", url="url_a", priority=85),
        SourceDetails(source_name="SEBI Press Release", title="B", url="url_b", priority=100) # Primary Source
    ]
    facts = [
        Fact(fact_type="funding_amount", original_value="$100M", normalized_value=100000000.0, confidence=1.0)
    ]
    
    # Scorer without conflicts
    conf = calculate_research_confidence(sources, facts, [])
    assert conf > 75
    
    # Scorer with open HIGH conflict
    conflicts = [
        ConflictAlert(conflict_type="VALUE_MISMATCH", fact_type="funding_amount", source_a="R", value_a="100M", source_b="E", value_b="120M", severity="HIGH", status="OPEN")
    ]
    conf_with_conflict = calculate_research_confidence(sources, facts, conflicts)
    assert conf_with_conflict < conf - 20

def test_research_eligibility_and_queue(db_session):
    """Verify research eligibility thresholds and priority ordering in queue."""
    story_repo = SQLStoryRepository(db_session)
    
    # 1. Eligible Story (High Importance)
    story_eligible = Story(
        title="Eligible High Imp",
        source_name="Reuters",
        source_url="r.com",
        article_url="r.com/1",
        published_at=datetime.utcnow(),
        category="FUNDING",
        content_hash="h1",
        importance_score=80,
        postability_score=60,
        final_score=70,
        status="APPROVED"
    )
    
    # 2. Ineligible Story (Low scores)
    story_ineligible = Story(
        title="Ineligible Low",
        source_name="Blog",
        source_url="b.com",
        article_url="b.com/1",
        published_at=datetime.utcnow(),
        category="MARKET",
        content_hash="h2",
        importance_score=40,
        postability_score=40,
        final_score=40,
        status="READY_FOR_REVIEW"
    )
    
    db_session.add_all([story_eligible, story_ineligible])
    db_session.commit()
    
    queue = story_repo.get_research_eligible_queue(min_importance=70, min_postability=75)
    
    assert len(queue) == 1
    assert queue[0].title == "Eligible High Imp"

def test_idempotent_research_runs(db_session):
    """Verify that multiple research iterations on the same story update, rather than duplicate entries."""
    story_repo = SQLStoryRepository(db_session)
    research_repo = SQLResearchRepository(db_session)
    
    story = Story(
        title="Idempotent Test",
        source_name="Reuters",
        source_url="r.com",
        article_url="r.com/idemp",
        published_at=datetime.utcnow(),
        category="FUNDING",
        content_hash="h3",
        importance_score=85,
        final_score=80,
        status="APPROVED",
        summary="A summary of the event."
    )
    db_session.add(story)
    db_session.commit()
    
    # First Run
    status_1 = research_story(db_session, story.id)
    assert db_session.query(ResearchReport).count() == 1
    
    # Second Run (Forces Rerun)
    status_2 = research_story(db_session, story.id, force_rerun=True)
    
    # Table counts MUST remain single, updating existing records instead of appending duplicates!
    assert db_session.query(ResearchReport).count() == 1
    assert db_session.query(ResearchSource).count() <= 2
