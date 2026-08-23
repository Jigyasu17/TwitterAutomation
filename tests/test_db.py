import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base, Story, StorySource

# Setup in-memory sqlite database for isolation
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

def test_story_creation(db_session):
    """Test creating a story and inserting it into the database."""
    now = datetime.utcnow()
    story = Story(
        title="BSE Sensex hits 80,000 milestone",
        source_name="Moneycontrol",
        source_url="https://moneycontrol.com",
        article_url="https://moneycontrol.com/news/123",
        published_at=now,
        category="MARKET",
        content_hash="mockhash123",
        status="NEW"
    )
    
    db_session.add(story)
    db_session.commit()
    
    saved_story = db_session.query(Story).filter_by(content_hash="mockhash123").first()
    assert saved_story is not None
    assert saved_story.title == "BSE Sensex hits 80,000 milestone"
    assert saved_story.category == "MARKET"
    assert saved_story.status == "NEW"

def test_story_source_relationship(db_session):
    """Test the cascading relationship between Story and StorySource."""
    now = datetime.utcnow()
    story = Story(
        title="BSE Sensex hits 80,000 milestone",
        source_name="Moneycontrol",
        source_url="https://moneycontrol.com",
        article_url="https://moneycontrol.com/news/123",
        published_at=now,
        category="MARKET",
        content_hash="mockhash123",
        status="NEW"
    )
    db_session.add(story)
    db_session.commit()

    source = StorySource(
        story_id=story.id,
        source_name="Economic Times",
        url="https://economictimes.indiatimes.com/news/123",
        published_at=now,
        title="Sensex Crosses 80K"
    )
    db_session.add(source)
    db_session.commit()

    assert len(story.sources) == 1
    assert story.sources[0].source_name == "Economic Times"

    # Test Cascade delete
    db_session.delete(story)
    db_session.commit()
    
    sources = db_session.query(StorySource).filter_by(story_id=story.id).all()
    assert len(sources) == 0
