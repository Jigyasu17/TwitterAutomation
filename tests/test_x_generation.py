import datetime
from unittest.mock import patch
from app.domain.models import StoryData, ResearchReportData, ResearchFactData
from app.drafts.engine import generate_draft_content, TWEET_LIMIT
from app.drafts.quality import is_headline_rewrite, score_draft, is_malformed_or_promotional
from app.research.intelligence import build_structured_intelligence
from app.drafts.ai_provider import is_ai_configured, generate_with_ai


def _story(title, event_type=None, company=None, facts=None, entities=None, category="STOCK"):
    report = None
    if facts is not None:
        report = ResearchReportData(story_id=1, status="COMPLETED", facts=facts, confidence_score=80)
    return StoryData(
        title=title,
        source_name="Economic Times",
        source_url="https://economictimes.com",
        article_url="https://economictimes.com/a",
        published_at=datetime.datetime.now(datetime.timezone.utc),
        category=category,
        content_hash="hash",
        company=company,
        event_type=event_type,
        entities=entities or {},
        research_report=report,
    )


def test_draft_is_not_just_a_headline_rewrite():
    title = "ABC Ltd acquires DEF Pvt Ltd for Rs 5,000 crore"
    fact = ResearchFactData(fact_type="acquisition_value", original_value="Rs 5,000 crore", normalized_value=50_000_000_000.0, currency="INR")
    story = _story(title, event_type="ACQUISITION", company="ABC Ltd", facts=[fact])
    result = generate_draft_content(story)
    assert not is_headline_rewrite(result.post_text, title)


def test_generated_post_has_a_hook_not_a_bare_headline():
    title = "XYZ Bank reports quarterly results"
    story = _story(title, event_type="EARNINGS", company="XYZ Bank", facts=[])
    result = generate_draft_content(story)
    # Even with zero facts, the engine must not just echo the raw headline back.
    assert result.post_text != title


def test_important_numbers_are_preserved_and_grounded():
    fact = ResearchFactData(fact_type="funding_amount", original_value="$50 million", normalized_value=50_000_000.0, currency="USD")
    story = _story("Startup raises new funding round", event_type="FUNDING", company="Navi", facts=[fact])
    result = generate_draft_content(story)
    assert "$50.0M" in result.post_text or any("$50.0M" in a["text"] for a in result.angles)


def test_event_specific_templates_differ_across_event_types():
    facts_funding = [ResearchFactData(fact_type="funding_amount", original_value="$10M", normalized_value=10_000_000.0, currency="USD")]
    facts_layoff = []
    funding_story = _story("Company raises funds", event_type="FUNDING", company="Navi", facts=facts_funding)
    layoff_story = _story("Company cuts jobs", event_type="LAYOFF", company="BigCorp", facts=facts_layoff)

    funding_result = generate_draft_content(funding_story)
    layoff_result = generate_draft_content(layoff_story)

    assert funding_result.hook_strategy != "" and layoff_result.hook_strategy != ""
    assert funding_result.post_text != layoff_result.post_text


def test_research_information_influences_the_draft():
    """A story WITH a completed research report must produce a materially
    different (richer) draft than the same story with no research at all."""
    fact = ResearchFactData(fact_type="profit", original_value="Rs 4,800 crore", normalized_value=48_000_000_000.0, currency="INR")
    with_research = _story("ABC Ltd posts strong results", event_type="PROFIT_UPDATE", company="ABC Ltd", facts=[fact])
    without_research = _story("ABC Ltd posts strong results", event_type="PROFIT_UPDATE", company="ABC Ltd", facts=None)

    with_result = generate_draft_content(with_research)
    without_result = generate_draft_content(without_research)

    assert with_result.post_text != without_result.post_text
    assert "Cr" in with_result.post_text or any("Cr" in a["text"] for a in with_result.angles)


def test_hallucinated_numbers_are_not_introduced_when_no_facts_exist():
    story = _story("Some Company announces a new initiative", event_type="OTHER", company="Some Company", facts=None)
    result = generate_draft_content(story)
    # No research facts were ever provided — the draft must not contain a
    # fabricated currency/percentage figure that didn't come from anywhere.
    from app.drafts.quality import NUMBER_RE
    assert not NUMBER_RE.search(result.post_text)


def test_character_limit_is_respected_for_every_angle():
    fact = ResearchFactData(fact_type="valuation", original_value="$2 billion", normalized_value=2_000_000_000.0, currency="USD")
    story = _story("Startup valuation soars after new round", event_type="FUNDING", company="Extremely Long Company Name Holdings Private Limited", facts=[fact])
    result = generate_draft_content(story)
    assert len(result.post_text) <= TWEET_LIMIT
    for angle in result.angles:
        assert len(angle["text"]) <= TWEET_LIMIT


def test_quality_score_penalizes_headline_rewrite_and_rewards_hook_plus_numbers():
    title = "ABC Ltd shares rose 8% after reporting strong quarterly results"
    rewrite_score, _ = score_draft(title, None, _story(title), [])
    good_post = "\U0001F4B0 ABC Ltd's results are in — profit of ₹4800.0Cr. This shows how ABC Ltd is actually doing financially."
    good_score, checks = score_draft(good_post, None, _story(title), [
        ResearchFactData(fact_type="profit", original_value="4800 crore", normalized_value=48_000_000_000.0, currency="INR")
    ])
    assert good_score > rewrite_score
    assert checks["has_hook"]
    assert checks["has_numbers"]


def test_ai_not_configured_by_default_and_falls_back_cleanly():
    """Production ships with AI_PROVIDER=none — this must never block drafting."""
    assert is_ai_configured() is False
    assert generate_with_ai("some facts") is None


def test_ai_failure_falls_back_to_deterministic_draft():
    story = _story("Zepto raises fresh funding from investors", event_type="FUNDING", company="Zepto", facts=[])
    with patch("app.drafts.engine.is_ai_configured", return_value=True), \
         patch("app.drafts.engine.generate_with_ai", side_effect=Exception("Ollama host unreachable")):
        result = generate_draft_content(story)
    assert result.ai_used is False
    assert result.post_text  # still produced a usable draft despite the AI path throwing


def test_structured_intelligence_flags_disputed_facts_and_confidence():
    fact = ResearchFactData(fact_type="funding_amount", original_value="$100M", normalized_value=100_000_000.0, currency="USD")
    story = _story("Company raises funding", event_type="FUNDING", company="Navi", facts=[fact])
    story.research_report.confidence_score = 85
    intel = build_structured_intelligence(story)
    assert intel.source_confidence_label == "HIGH"
    assert intel.has_research is True
    assert "number_led" in intel.potential_angles or "consequence" in intel.potential_angles


# --- Phase 3 quality-gate additions: clickbait / malformed-output rejection ---

def test_clickbait_language_is_rejected():
    assert is_malformed_or_promotional("You won't believe what ABC Ltd just announced!!!") is not None
    assert is_malformed_or_promotional("This is a mind-blowing game-changer for investors") is not None


def test_excessive_punctuation_and_shouting_are_rejected():
    assert is_malformed_or_promotional("ABC LTD JUST CRUSHED IT!!! HUGE NEWS!!!") is not None


def test_malformed_ai_artifacts_are_rejected():
    assert is_malformed_or_promotional('{"post": "ABC Ltd raises funds"}') is not None
    assert is_malformed_or_promotional("I cannot assist with generating this content") is not None
    assert is_malformed_or_promotional("") is not None
    assert is_malformed_or_promotional("ok") is not None


def test_clean_grounded_post_is_not_flagged():
    good_post = "\U0001F4B0 ABC Ltd's results are in — profit of ₹4800.0Cr. This shows how ABC Ltd is actually doing financially."
    assert is_malformed_or_promotional(good_post) is None


def test_engine_never_returns_malformed_output_even_when_ai_returns_garbage():
    """If a configured AI provider ever returned garbled/promotional text,
    the engine's quality gate must reject it and fall back cleanly — AI
    failure (or bad output) must never break the pipeline or reach a user."""
    fact = ResearchFactData(fact_type="funding_amount", original_value="$10M", normalized_value=10_000_000.0, currency="USD")
    story = _story("Navi raises new funding round", event_type="FUNDING", company="Navi", facts=[fact])
    with patch("app.drafts.engine.is_ai_configured", return_value=True), \
         patch("app.drafts.engine.generate_with_ai", return_value="SHOCKING!!! You won't believe this game-changer!!!"):
        result = generate_draft_content(story)
    assert result.ai_used is False  # the garbage candidate was rejected, not selected
    assert is_malformed_or_promotional(result.post_text) is None


def test_comma_grouped_currency_figures_are_not_truncated():
    """
    Regression test: '₹29,967 Cr' was previously extracted as '₹29' — the
    regex's numeric portion stopped at the first comma, silently truncating
    a real figure into a much smaller, wrong one (a fact-safety violation
    worse than omitting the number entirely). Found via the Phase 8 live
    10-story showcase, not a synthetic case.
    """
    from app.research.fact_extractor import extract_facts_from_text
    facts = extract_facts_from_text("Infosys Shares Jump 5%; Market Valuation Surges by ₹29,967 Cr")
    valuation = next(f for f in facts if f.fact_type == "valuation")
    assert valuation.normalized_value == 299_670_000_000.0
    assert "29,967" in valuation.original_value

    facts2 = extract_facts_from_text("Jio Platforms Q1 results: Profit rises 9.2% to ₹7,764 cr, revenue up 12%")
    profit = next(f for f in facts2 if f.fact_type == "profit")
    assert profit.normalized_value == 77_640_000_000.0
    assert "7,764" in profit.original_value


def test_unnecessary_company_name_repetition_is_penalized():
    story = _story("ABC Ltd reports results", company="ABC Ltd")
    spammy = "ABC Ltd ABC Ltd ABC Ltd announces ABC Ltd results for ABC Ltd shareholders"
    clean = "\U0001F4B0 ABC Ltd's results are in — profit of ₹4800.0Cr. This shows how the company is actually doing financially."
    spammy_score, spammy_checks = score_draft(spammy, None, story, [])
    clean_score, clean_checks = score_draft(clean, None, story, [
        ResearchFactData(fact_type="profit", original_value="4800 crore", normalized_value=48_000_000_000.0, currency="INR")
    ])
    assert spammy_checks["no_unnecessary_company_repetition"] is False
    assert clean_checks["no_unnecessary_company_repetition"] is True
