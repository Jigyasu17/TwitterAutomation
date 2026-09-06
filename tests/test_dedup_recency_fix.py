"""
Regression tests for the P0 dedup fix: the candidate pool for
deduplication must be recency-ordered, not score-ordered, or brand-new
same-day duplicates (which start at final_score=0, before classification)
silently vanish from comparison once the database accumulates more
already-scored stories than the old fixed limit (150).

Reproduces the exact live-audit failure: 5 of 12 real "NSE IPO" articles
collected within 48 hours were never clustered because the dedup pool was
`get_stories(status="any", limit=150)` sorted by score — a pool entirely
filled with old high-scorers, containing zero not-yet-scored candidates.
"""
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base, Story
from app.processing.deduplication import add_or_merge_story, calculate_similarity


def _make_old_high_scoring_story(i: int, now: datetime.datetime) -> Story:
    return Story(
        title=f"Old high scoring story number {i} about something unrelated",
        source_name="Reuters",
        source_url="https://reuters.com",
        article_url=f"https://reuters.com/old-story-{i}",
        published_at=now - datetime.timedelta(days=60),
        category="MARKET",
        content_hash=f"old_hash_{i}",
        final_score=90,  # deliberately high — these must not crowd out new candidates
        importance_score=90,
        status="APPROVED",
    )


def test_new_duplicate_is_found_even_with_over_150_old_high_scoring_stories(db_session):
    """
    The exact regression scenario from the brief: insert >150 old
    high-scoring stories, then two new, highly similar articles — the
    second must still be recognized as a duplicate of the first.
    """
    now = datetime.datetime.utcnow()

    # 1. Flood the DB with 200 old, high-scoring stories — more than the
    # dedup pool's old fixed limit of 150.
    old_stories = [_make_old_high_scoring_story(i, now) for i in range(200)]
    db_session.add_all(old_stories)
    db_session.commit()
    assert db_session.query(Story).count() == 200

    # 2. Two new, essentially-identical same-day articles.
    story_a = {
        "title": "NSE gets regulatory nod for Rs 30,000 cr IPO, the biggest so far",
        "source_name": "Rediff",
        "source_url": "https://rediff.com",
        "article_url": "https://rediff.com/nse-ipo-nod",
        "published_at": now,
        "category": "IPO",
        "summary": "NSE cleared for its own IPO.",
    }
    story_b = {
        "title": "NSE gets regulatory nod for Rs 30,000 crore IPO, the biggest so far",
        "source_name": "The Indian Express",
        "source_url": "https://indianexpress.com",
        "article_url": "https://indianexpress.com/nse-ipo-nod",
        "published_at": now + datetime.timedelta(minutes=20),
        "category": "IPO",
        "summary": "NSE cleared for its own IPO by the regulator.",
    }

    first = add_or_merge_story(db_session, story_a)
    second = add_or_merge_story(db_session, story_b)

    # Must merge into ONE story, not two — this is exactly what silently
    # broke when the dedup pool was score-ordered and capped at 150.
    assert second.id == first.id
    assert len(first.sources) == 2
    # The flood of old stories must not have been touched/duplicated.
    assert db_session.query(Story).count() == 201


def test_new_duplicate_with_different_wording_is_found_despite_old_story_flood(db_session):
    """
    Same flood scenario, but the two new articles are worded completely
    differently (the exact brief example) — this exercises Level 5 (event
    fingerprint), not Level 4 (title similarity), since these two titles
    share almost no text.
    """
    now = datetime.datetime.utcnow()
    old_stories = [_make_old_high_scoring_story(i, now) for i in range(180)]
    db_session.add_all(old_stories)
    db_session.commit()

    story_a = {
        "title": "NSE gets regulatory nod for Rs 30,000 cr IPO",
        "source_name": "Reuters",
        "source_url": "https://reuters.com",
        "article_url": "https://reuters.com/nse-a",
        "published_at": now,
        "category": "IPO",
    }
    story_b = {
        "title": "India's NSE eyes September listing after regulator clears IPO",
        "source_name": "Livemint",
        "source_url": "https://livemint.com",
        "article_url": "https://livemint.com/nse-b",
        "published_at": now + datetime.timedelta(hours=2),
        "category": "IPO",
    }

    # Confirm these two titles genuinely have low raw-text similarity, so a
    # pass here proves Level 5 (event fingerprint), not Level 4, did the work.
    assert calculate_similarity(story_a["title"], story_b["title"]) < 0.6

    first = add_or_merge_story(db_session, story_a)
    second = add_or_merge_story(db_session, story_b)

    assert second.id == first.id
    assert len(first.sources) == 2


def test_recent_stories_pool_excludes_stories_outside_the_lookback_window(db_session):
    """The recency-first pool must still respect the lookback window — it
    should not become an unbounded "everything ever" scan either."""
    from app.repositories.sqlite.story_repository import SQLStoryRepository

    now = datetime.datetime.utcnow()
    recent = Story(
        title="Recent story", source_name="Reuters", source_url="r.com",
        article_url="r.com/recent", published_at=now, category="MARKET",
        content_hash="recent_hash", final_score=10, status="NEW",
    )
    ancient = Story(
        title="Ancient story", source_name="Reuters", source_url="r.com",
        article_url="r.com/ancient", published_at=now - datetime.timedelta(days=400),
        category="MARKET", content_hash="ancient_hash", final_score=95, status="APPROVED",
    )
    db_session.add_all([recent, ancient])
    db_session.commit()

    repo = SQLStoryRepository(db_session)
    pool = repo.get_recent_stories_for_dedup(lookback_days=7, limit=500)
    titles = {s.title for s in pool}
    assert "Recent story" in titles
    assert "Ancient story" not in titles


def test_higher_quality_source_is_promoted_to_primary_representation(db_session):
    """
    Requirement 6: when a more authoritative source reports the same
    event as an already-saved lower-tier source, it should become the
    primary (displayed) representation — not stay buried as a mere
    confirming source under the weaker article's title.
    """
    now = datetime.datetime.utcnow()
    story_a = {
        "title": "Jio Platforms IPO gets clearance",
        "source_name": "Random Aggregator Blog",  # Tier 4
        "source_url": "https://aggregator.example",
        "article_url": "https://aggregator.example/jio-a",
        "published_at": now,
        "category": "IPO",
    }
    story_b = {
        "title": "Jio Platforms IPO gets clearance from regulator",
        "source_name": "Reuters",  # Tier 2 — strictly higher quality
        "source_url": "https://reuters.com",
        "article_url": "https://reuters.com/jio-b",
        "published_at": now + datetime.timedelta(minutes=30),
        "category": "IPO",
    }

    first = add_or_merge_story(db_session, story_a)
    merged = add_or_merge_story(db_session, story_b)

    assert merged.id == first.id
    assert merged.source_name == "Reuters"  # promoted
    assert len(merged.sources) == 2  # both still preserved as confirming sources
    # Identity fields must NOT be rewritten by promotion (would corrupt
    # collection_job.py's new-vs-merged article_url comparison).
    assert merged.article_url == "https://aggregator.example/jio-a"


def test_lower_quality_source_does_not_demote_an_existing_higher_quality_primary(db_session):
    now = datetime.datetime.utcnow()
    story_a = {
        "title": "Jio Platforms IPO gets clearance",
        "source_name": "Reuters",
        "source_url": "https://reuters.com",
        "article_url": "https://reuters.com/jio-a",
        "published_at": now,
        "category": "IPO",
    }
    story_b = {
        "title": "Jio Platforms IPO gets clearance, sources say",
        "source_name": "Random Aggregator Blog",
        "source_url": "https://aggregator.example",
        "article_url": "https://aggregator.example/jio-b",
        "published_at": now + datetime.timedelta(minutes=30),
        "category": "IPO",
    }

    first = add_or_merge_story(db_session, story_a)
    merged = add_or_merge_story(db_session, story_b)

    assert merged.id == first.id
    assert merged.source_name == "Reuters"  # unchanged — Reuters stays primary
