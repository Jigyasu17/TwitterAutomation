import datetime
from app.domain.models import StoryData, ResearchReportData, ResearchFactData
from app.drafts.builder import generate_post_text, _truncate, _format_amount, TWEET_LIMIT
from app.database.models import Story
from app.repositories.sqlite import SQLStoryRepository
from app.repositories.sqlite.draft_repository import SQLDraftRepository
from app.drafts.orchestrator import generate_draft


def _make_story(event_type=None, company="Zepto", facts=None, why_it_matters=None, article_url="https://example.com/a"):
    report = None
    if facts is not None or why_it_matters is not None:
        report = ResearchReportData(
            story_id=1,
            status="COMPLETED",
            why_it_matters=why_it_matters,
            facts=facts or []
        )
    return StoryData(
        title="Zepto raises fresh funding from investors",
        source_name="MoneyControl",
        source_url="https://moneycontrol.com",
        article_url=article_url,
        published_at=datetime.datetime.now(datetime.timezone.utc),
        category="FUNDING",
        content_hash="hash1",
        company=company,
        event_type=event_type,
        research_report=report
    )


def test_funding_hook_uses_research_fact_amount_and_plain_explainer():
    fact = ResearchFactData(fact_type="funding_amount", original_value="$100 million", normalized_value=100_000_000.0, currency="USD")
    story = _make_story(event_type="FUNDING", facts=[fact])
    post_text, thread, headline, subheadline = generate_post_text(story)

    assert "Zepto" in post_text
    assert "$100.0M" in post_text
    assert len(post_text) <= TWEET_LIMIT
    # Plain-language explainer is combined into the same tweet when it fits,
    # rather than being formal analyst language like "capital infusion".
    assert "grow faster" in post_text
    assert "capital infusion" not in post_text

def test_stock_movement_hook_shows_direction_and_percentage():
    fact = ResearchFactData(fact_type="stock_movement", original_value="5%", normalized_value=-5.2)
    story = _make_story(event_type="STOCK_MOVEMENT", company="IndusInd Bank", facts=[fact])
    post_text, thread, headline, subheadline = generate_post_text(story)

    assert "dropped" in post_text
    assert "5.2%" in post_text

def test_falls_back_to_title_with_hook_prefix_when_no_template_matches():
    story = _make_story(event_type="OTHER", facts=[])
    post_text, thread, headline, subheadline = generate_post_text(story)

    assert story.title in post_text
    assert post_text != story.title  # still gets a retention hook cue, not the raw headline

def test_explainer_overflow_moves_to_thread_when_combined_is_too_long():
    # An unusually long company name forces hook+explainer past the 280 limit,
    # so the explainer must fall back to the thread instead of being dropped.
    long_name = "Extremely Long Multinational Conglomerate Holding Company Group Name " * 4
    story = _make_story(event_type="FUNDING", company=long_name, facts=[])
    post_text, thread, headline, subheadline = generate_post_text(story)

    assert len(post_text) <= TWEET_LIMIT
    assert "grow faster" not in post_text
    assert thread is not None
    assert any("grow faster" in t for t in thread)

def test_source_link_lands_in_thread_when_present():
    story = _make_story(event_type="FUNDING", article_url="https://example.com/article")
    post_text, thread, headline, subheadline = generate_post_text(story)

    assert thread is not None
    assert any("https://example.com/article" in t for t in thread)

def test_google_news_url_shows_outlet_name_not_the_ugly_redirect_link():
    # Google News RSS links are obfuscated redirects with no reliable way to
    # resolve the real URL without an unofficial/fragile decoder — show the
    # outlet name instead of an unclickable, ugly link.
    story = _make_story(
        event_type="FUNDING",
        article_url="https://news.google.com/rss/articles/CBMiabcdef123456"
    )
    post_text, thread, headline, subheadline = generate_post_text(story)

    assert thread is not None
    assert any(t == "Source: MoneyControl" for t in thread)
    assert not any("news.google.com" in t for t in thread)

def test_wire_service_or_regulator_name_is_not_treated_as_the_company():
    # A story where the classifier mistakenly extracted a cited wire service
    # or regulator name as "the company" must not produce a nonsensical hook
    # like "SEBI just hit the stock market!" or "Reuters is going public!".
    for bad_name in ["Reuters", "SEBI", "sebi", "Bloomberg"]:
        story = _make_story(event_type="IPO_LISTING", company=bad_name, facts=[])
        post_text, thread, headline, subheadline = generate_post_text(story)
        assert bad_name not in post_text
        assert "This company" in post_text

def test_no_source_url_omits_source_line_from_thread():
    story = _make_story(event_type="OTHER", article_url="")
    post_text, thread, headline, subheadline = generate_post_text(story)

    if thread:
        assert not any(t.startswith("Source:") for t in thread)

def test_truncate_respects_limit_and_adds_ellipsis():
    long_text = "x" * 400
    truncated = _truncate(long_text, limit=280)
    assert len(truncated) == 280
    assert truncated.endswith("…")

def test_truncate_leaves_short_text_untouched():
    assert _truncate("short text") == "short text"

def test_format_amount_crore_for_inr():
    fact = ResearchFactData(fact_type="valuation", original_value="50 crore", normalized_value=500_000_000.0, currency="INR")
    assert "Cr" in _format_amount(fact)

def test_format_amount_billion_for_usd():
    fact = ResearchFactData(fact_type="valuation", original_value="$2 billion", normalized_value=2_000_000_000.0, currency="USD")
    assert "B" in _format_amount(fact)

def test_format_amount_falls_back_to_original_on_bad_value():
    fact = ResearchFactData(fact_type="valuation", original_value="unclear amount", normalized_value="not-a-number", currency="USD")
    assert _format_amount(fact) == "unclear amount"


def test_generate_draft_is_idempotent_and_forceable(db_session):
    """Mirrors test_idempotent_research_runs in tests/test_milestone3.py: a
    regeneration must not silently wipe an edited or posted draft unless forced."""
    story_repo = SQLStoryRepository(db_session)
    draft_repo = SQLDraftRepository(db_session)

    story_orm = Story(
        title="Test Corp raises funding",
        source_name="Reuters",
        source_url="r.com",
        article_url="r.com/idempotent-draft",
        published_at=datetime.datetime.utcnow(),
        category="FUNDING",
        content_hash="draft_idempotency_hash",
        company="Test Corp",
        event_type="FUNDING",
        final_score=80,
        status="APPROVED"
    )
    db_session.add(story_orm)
    db_session.commit()

    # First generation
    first = generate_draft(story_repo, draft_repo, story_orm.id)
    assert first.status == "NEW"

    # Simulate a manual edit
    first.edited_text = "My manually edited tweet"
    first.status = "EDITED"
    draft_repo.save_draft(first)

    # Regenerating without force must return the edited draft untouched
    second = generate_draft(story_repo, draft_repo, story_orm.id)
    assert second.status == "EDITED"
    assert second.edited_text == "My manually edited tweet"

    # Forcing must overwrite it
    third = generate_draft(story_repo, draft_repo, story_orm.id, force_regenerate=True)
    assert third.status == "NEW"
    assert third.id == first.id  # same draft row, not a duplicate

    # Only one draft should ever exist for this story
    all_drafts = draft_repo.get_drafts(status="all")
    assert sum(1 for d in all_drafts if d.story_id == story_orm.id) == 1
