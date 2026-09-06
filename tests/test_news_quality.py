import datetime
from app.processing.classifier import calculate_scores, extract_entities, identify_event_type
from app.processing.source_quality import get_source_tier, get_source_quality_score
from app.processing.relevance import calculate_india_relevance
from app.processing.noise_filter import detect_noise
from app.processing.deduplication import add_or_merge_story


def test_source_tiers_rank_regulators_above_aggregators():
    assert get_source_tier("SEBI") == 1
    assert get_source_tier("Reuters") == 2
    assert get_source_tier("Random Aggregator Blog") == 4
    assert get_source_quality_score("SEBI") > get_source_quality_score("Random Aggregator Blog")


def test_india_relevance_gate_scores_direct_india_stories_higher():
    entities = extract_entities("SEBI bars XYZ from markets", "")
    india_score = calculate_india_relevance("SEBI bars XYZ Ltd from markets", "", entities, country="India")
    foreign_score = calculate_india_relevance("A small US retailer opens a new store", "", {}, country="United States")
    assert india_score > foreign_score
    assert india_score >= 70


def test_global_macro_gets_partial_india_credit_not_full_or_zero():
    score = calculate_india_relevance("Fed rate hike sends global markets lower", "", {}, country=None)
    assert 40 <= score < 70


def test_noise_filter_flags_listicle_with_no_material_backing():
    is_noise, penalty, reasons = detect_noise(
        "5 stocks to watch today", "Here are some picks", entities={}, event_type=None, has_numeric_facts=False
    )
    assert is_noise is True
    assert penalty > 0
    assert reasons


def test_noise_filter_discounts_but_does_not_reject_grounded_story_shaped_like_a_listicle():
    # "things investors should know" is a listicle-shaped phrase, but this
    # one is grounded in a real regulatory fine — discount it, don't nuke it.
    is_noise, penalty, reasons = detect_noise(
        "5 things investors should know about SEBI's record Rs 500 crore fine on XYZ Bank",
        "",
        entities={"Companies": ["XYZ Bank"]},
        event_type="REGULATORY_ACTION",
        has_numeric_facts=True,
    )
    assert is_noise is False
    assert 0 < penalty < 45  # discounted, not the full noise penalty


def test_noise_filter_passes_clean_material_headline():
    entities = extract_entities("Zepto raises $200 million in new funding round", "")
    is_noise, penalty, reasons = detect_noise(
        "Zepto raises $200 million in new funding round", "", entities, "FUNDING", True
    )
    assert is_noise is False
    assert penalty == 0


def test_scoring_down_ranks_noise_and_up_ranks_material_india_story():
    entities_noise = extract_entities("Top 5 stocks to watch today", "")
    imp_noise, post_noise, conf_noise, final_noise, breakdown_noise = calculate_scores(
        "Top 5 stocks to watch today", "Market experts say these may rise", "Random Blog", 1,
        entities=entities_noise, event_type=None, country=None,
    )

    entities_material = extract_entities("SEBI imposes Rs 500 crore penalty on XYZ Bank", "")
    event_type_material = identify_event_type("SEBI imposes Rs 500 crore penalty on XYZ Bank")
    imp_material, post_material, conf_material, final_material, breakdown_material = calculate_scores(
        "SEBI imposes Rs 500 crore penalty on XYZ Bank", "Regulatory action taken", "Economic Times", 2,
        entities=entities_material, event_type=event_type_material, country="India",
    )

    assert final_material > final_noise
    assert breakdown_noise["noise_penalty"] > 0
    assert breakdown_material["india_relevance"] > breakdown_noise["india_relevance"]
    assert "key_reason" in breakdown_material


def test_freshness_plus_importance_beats_freshness_alone():
    """A 2-hour-old major regulatory event should outrank a 5-minute-old irrelevant filler story."""
    now = datetime.datetime.utcnow()
    entities = extract_entities("SEBI bars XYZ Bank from markets after probe", "")
    event_type = identify_event_type("SEBI bars XYZ Bank from markets after probe")
    _, _, _, final_major_but_older, _ = calculate_scores(
        "SEBI bars XYZ Bank from markets after probe", "", "Economic Times", 1,
        entities=entities, event_type=event_type, country="India",
        published_at=now - datetime.timedelta(hours=2),
    )

    _, _, _, final_fresh_but_trivial, _ = calculate_scores(
        "Company attends industry networking event", "CEO felicitated at gala", "Random Blog", 1,
        entities={}, event_type=None, country=None,
        published_at=now - datetime.timedelta(minutes=5),
    )

    assert final_major_but_older > final_fresh_but_trivial


def test_calculate_scores_still_works_without_optional_context(monkeypatch=None):
    """Backward compatibility: existing callers passing only the original 4 positional args must keep working."""
    imp, post, conf, final, breakdown = calculate_scores("Tata Motors raises $1 Billion", "EV funding", "Reuters", 1)
    assert 0 <= imp <= 100
    assert 0 <= final <= 100
    assert breakdown["india_relevance"] == 0  # no country/entities passed — neutral default, not a crash


def test_event_fingerprint_clusters_differently_worded_coverage_of_the_same_event(db_session):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base

    now = datetime.datetime.utcnow()

    story_a = {
        "title": "Tata Motors reports quarterly profit surge on strong sales",
        "source_name": "Reuters",
        "source_url": "https://reuters.com",
        "article_url": "https://reuters.com/tata-a",
        "published_at": now,
        "category": "STOCK",
        "summary": "Profit rose sharply on strong demand.",
    }
    story_b = {
        "title": "Tata Motors quarterly earnings beat estimates as profit jumps",
        "source_name": "Economic Times",
        "source_url": "https://economictimes.com",
        "article_url": "https://economictimes.com/tata-b",
        "published_at": now + datetime.timedelta(hours=1),
        "category": "STOCK",
        "summary": "Earnings beat analyst estimates for the quarter.",
    }

    first = add_or_merge_story(db_session, story_a)
    second = add_or_merge_story(db_session, story_b)

    # Only ~0.50 raw title-text similarity between the two (well under the
    # 0.8 Level-4 threshold) but same company + same PROFIT_UPDATE event type
    # within an hour — Level 5 (event fingerprint) must cluster them.
    assert second.id == first.id
    assert len(first.sources) == 2
