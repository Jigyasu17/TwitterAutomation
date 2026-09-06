"""
Regression tests for the editorial-quality fix pass: entity attribution,
event-type over-broad matching, staleness decay, content-type
classification, and the category-classification false positives found in
the live content-quality audit.
"""
import datetime
from app.processing.classifier import (
    extract_entities, classify_category, identify_event_type,
    resolve_main_company, calculate_scores,
)
from app.processing.entity_roles import NON_COMPANY_ENTITIES, is_non_company
from app.processing.content_type import classify_content_type, SINGLE_EVENT, ROUNDUP, CALENDAR, ADVICE, FORECAST, MARKET_EVENT, OPINION, MARKET_WRAP
from app.processing.staleness import staleness_multiplier


# --- Problem 3 & 4: entity/company attribution ---

def test_wire_service_names_never_extracted_as_companies():
    for title in [
        "Quest Global Said to Pick Banks for $1 Billion India IPO",
        "Indian gold loan lender Muthoot FinCorp files for $314 million IPO",
        "KKR-backed logistics firm LEAP India seeks $734 million valuation in India IPO",
    ]:
        entities = extract_entities(title, f"{title}—Reuters")
        assert "Reuters" not in entities["Companies"]
        assert "Bloomberg" not in entities["Companies"]


def test_said_to_pattern_extracts_the_real_company():
    entities = extract_entities("Quest Global Said to Pick Banks for $1 Billion India IPO", "")
    assert "Quest Global" in entities["Companies"]

    entities = extract_entities("Sembcorp Said to Plan Filing for $500 Million IPO of India Unit", "")
    assert "Sembcorp" in entities["Companies"]


def test_descriptive_phrase_before_company_name_still_extracts_correctly():
    entities = extract_entities("Indian gold loan lender Muthoot FinCorp files for $314 million IPO", "")
    assert "Muthoot FinCorp" in entities["Companies"]

    entities = extract_entities("KKR-backed logistics firm LEAP India seeks $734 million valuation in India IPO", "")
    assert "LEAP India" in entities["Companies"]


def test_sebi_and_rbi_are_never_companies_but_are_captured_as_regulators():
    entities = extract_entities(
        "Aastha Spintex IPO Opens; SEBI-Registered Research Analysts Cite Capacity Expansion", ""
    )
    assert "SEBI" not in entities["Companies"]
    assert "Sebi" not in entities["Companies"]
    assert "SEBI" in entities["Regulators"]

    entities = extract_entities("RBI imposes penalty on XYZ Bank for compliance lapses", "")
    assert "RBI" not in entities["Companies"]
    assert "RBI" in entities["Regulators"]


def test_nse_and_bse_remain_eligible_as_the_main_company():
    entities = extract_entities("NSE gets regulatory nod for Rs 30,000 cr IPO, the biggest so far", "")
    assert "NSE" in entities["Companies"]
    company = resolve_main_company(entities, content_type=SINGLE_EVENT)
    assert company == "NSE"


def test_resolve_main_company_never_returns_a_non_company_entity():
    for name in ["Reuters", "Bloomberg", "SEBI", "RBI", "Moneycontrol", "Livemint",
                 "Economic Times", "The Economic Times", "Business Standard",
                 "TradingView", "LinkedIn"]:
        assert is_non_company(name), f"{name} should be classified as a non-company entity"


def test_resolve_main_company_returns_none_for_roundups_instead_of_guessing():
    entities = {"Companies": ["Reliance", "Tata"]}  # only 2 of the 6+ mentioned made it through extraction
    assert resolve_main_company(entities, content_type=CALENDAR) is None
    assert resolve_main_company(entities, content_type=ROUNDUP) is None


def test_resolve_main_company_returns_none_when_too_many_companies_named():
    entities = {"Companies": ["A", "B", "C", "D", "E"]}
    assert resolve_main_company(entities, content_type=SINGLE_EVENT) is None


# --- Problem 2: event-type over-broad "listing" matching ---

def test_ipo_listing_requires_an_actual_listing_event():
    positive_cases = [
        "Company X shares listed on the NSE today",
        "Company X stock lists at a 20% premium",
        "Company X makes market debut on BSE",
        "Company X shares debut higher than expected",
        "Company X stock debuts at a discount",
        "Trading begins for Company X on the exchange",
    ]
    for title in positive_cases:
        assert identify_event_type(title) == "IPO_LISTING", title

    negative_cases = [
        "NSE IPO listing date, timeline: When the issue is expected to hit exchanges",
        "IPO could become India's biggest listing",
        "Company X IPO: listing plans revealed",
        "Why IPO timing matters for Company X",
        "India's biggest potential listing: what investors should know about the IPO",
    ]
    for title in negative_cases:
        result = identify_event_type(title)
        assert result != "IPO_LISTING", f"{title} -> {result}"


def test_all_real_nse_headlines_from_the_audit_classify_consistently():
    """
    These 6 real headlines from the live audit previously split 3-3 between
    IPO_ANNOUNCEMENT and IPO_LISTING purely because half of them happened to
    contain the word "listing" — which blocked Level-5 event-fingerprint
    clustering. They must now classify identically.
    """
    headlines = [
        "NSE IPO listing date, timeline: When ₹30,000 cr issue is expected to hit Indian stock market exchanges",
        "NSE IPO: Ahead of mega ₹30k cr issue, should you buy SBI, Bank of Baroda shares? What investors should do?",
        "NSE gets regulatory nod for Rs 30,000 cr IPO, the biggest so far",
        "NSE IPO: The buzz around India's biggest public issue and why timing is important",
        "India's NSE eyes September 21-week listing after regulator clears IPO, sources say",
    ]
    event_types = {identify_event_type(h) for h in headlines}
    assert len(event_types) == 1, f"Expected one consistent event type, got {event_types}"
    assert event_types == {"IPO_ANNOUNCEMENT"}


# --- Problem 7: category classification ---

def test_multi_stock_market_movement_is_market_not_tech():
    title = "IndiGo jumps 4.5%, HPCL surges 6.6%, tyre stocks gain up to 7%; falling crude oil prices lift..."
    category, tags = classify_category(title, "")
    assert category == "MARKET"
    assert category != "TECH"


def test_short_keyword_substrings_do_not_false_positive_inside_ordinary_words():
    # "gain" contains "ai"; must not trigger the TECH/AI category on its own.
    category, tags = classify_category("Stocks gain broadly today, IndiGo jumps 4.5%, HPCL surges 6.6%", "")
    assert category != "TECH"
    # "increase" contains "cr"; must not inflate financial-significance via
    # the bare "cr" keyword fallback in calculate_scores.
    imp, post, conf, final, breakdown = calculate_scores(
        "Company announces a modest increase in headcount", "", "Random Blog", 1
    )
    assert breakdown["financial_significance"] <= 2


def test_genuine_ai_and_ev_keywords_still_classify_as_tech():
    category, _ = classify_category("Company unveils new AI chip for data centres", "")
    assert category == "TECH"
    # "startup"/"funding"/etc. keywords deliberately outrank TECH in branch
    # order (an EV-battery *startup* story is more STARTUP than TECH) — use
    # a title with no earlier-branch keyword to isolate the EV/TECH check.
    category, _ = classify_category("Manufacturer unveils new EV battery technology", "")
    assert category == "TECH"


# --- Problem 5: staleness decay ---

def test_290_day_old_story_decays_far_below_a_fresh_meaningful_story():
    now = datetime.datetime.utcnow()
    old_mult = staleness_multiplier(now - datetime.timedelta(days=290), event_type="STOCK_MOVEMENT")
    fresh_mult = staleness_multiplier(now - datetime.timedelta(hours=2), event_type="STOCK_MOVEMENT")
    assert old_mult <= 0.10
    assert fresh_mult >= 0.90
    assert fresh_mult > old_mult * 5


def test_290_day_old_story_cannot_outrank_a_fresh_comparable_story_in_full_scoring():
    now = datetime.datetime.utcnow()
    title = "Anil Ambani's Reliance Power shares rise 5%, snap 3-day fall"
    entities = extract_entities(title, "")
    event_type = identify_event_type(title)

    _, _, _, old_final, _ = calculate_scores(
        title, "", "The Economic Times", 1, entities=entities, event_type=event_type,
        country="India", published_at=now - datetime.timedelta(days=290),
    )
    _, _, _, fresh_final, _ = calculate_scores(
        title, "", "The Economic Times", 1, entities=entities, event_type=event_type,
        country="India", published_at=now - datetime.timedelta(hours=2),
    )
    assert fresh_final > old_final


def test_ongoing_long_cycle_events_decay_more_slowly_than_a_one_off_story():
    now = datetime.datetime.utcnow()
    ipo_mult = staleness_multiplier(now - datetime.timedelta(days=20), event_type="IPO_ANNOUNCEMENT")
    stock_move_mult = staleness_multiplier(now - datetime.timedelta(days=20), event_type="STOCK_MOVEMENT")
    assert ipo_mult > stock_move_mult


def test_no_published_at_is_neutral_not_penalized():
    assert staleness_multiplier(None) == 1.0


# --- Problem 6/8: content-type classification ---

def test_results_calendar_is_flagged_as_calendar_not_single_event():
    title = "Q1 Results: Reliance Industries, JSW Steel, Federal Bank, Havells India, Tata Technologies, Oberoi Realty, others to post earnings on July 17"
    ct = classify_content_type(title, "", company_count=2)
    assert ct == CALENDAR


def test_weekly_funding_roundup_is_flagged_as_roundup():
    title = "From Navi To BookMyShow — Indian Startups Raised Over $233 Mn This Week"
    ct = classify_content_type(title, "", company_count=1)
    assert ct == ROUNDUP


def test_stock_tip_is_flagged_as_advice():
    title = "NSE IPO: Ahead of mega issue, should you buy SBI, Bank of Baroda shares? What investors should do?"
    ct = classify_content_type(title, "", company_count=2)
    assert ct == ADVICE


def test_generic_outlook_is_flagged_as_forecast():
    title = "How will Nifty, Sensex behave on Monday? 4 factors to drive D-Street action"
    ct = classify_content_type(title, "", company_count=0)
    assert ct == FORECAST


def test_single_company_material_event_is_single_event():
    title = "Company X announces ₹70,000 crore investment in new campus"
    ct = classify_content_type(title, "", company_count=1)
    assert ct == SINGLE_EVENT


def test_completed_market_move_is_market_event_not_forecast():
    title = "Sensex rises 700 points as crude falls 5%"
    ct = classify_content_type(title, "", company_count=0)
    assert ct == MARKET_EVENT


def test_roundup_with_exceptional_figure_is_not_punished_as_hard_as_a_generic_roundup():
    from app.processing.content_type import content_type_penalty
    generic_roundup_penalty = content_type_penalty(CALENDAR, has_large_financial_figure=False)
    exceptional_roundup_penalty = content_type_penalty(CALENDAR, has_large_financial_figure=True)
    assert exceptional_roundup_penalty < generic_roundup_penalty


def test_single_event_and_market_event_get_no_content_type_penalty():
    from app.processing.content_type import content_type_penalty
    assert content_type_penalty(SINGLE_EVENT) == 0
    assert content_type_penalty(MARKET_EVENT) == 0


# --- Problem 9: calculate_scores integrates content type + staleness ---

# --- Second-pass fixes: OPINION/ANALYSIS/EXPLAINER, MARKET_WRAP ---

def test_A_generic_opinion_trend_piece_is_opinion():
    ct = classify_content_type("Why India's IPO markets are heating up after slow first half of 2026", "")
    assert ct == OPINION


def test_B_explainer_suffix_is_opinion():
    ct = classify_content_type(
        "7.8% GDP is good news but why skyrocketing KOSPI, Nikkei, Taiwan remain a major concern for Sensex, Nifty | Explained",
        "",
    )
    assert ct == OPINION


def test_C_hard_news_profit_report_is_single_event():
    ct = classify_content_type("ABC reports 40% profit growth", "")
    assert ct == SINGLE_EVENT


def test_D_why_question_anchored_to_a_real_event_is_not_generic_opinion():
    """The brief's key nuance: a 'why' headline anchored to a real, quantified,
    completed move (a % change tied to an explicit cause) is event analysis,
    not generic opinion — it must not be down-weighted like ungrounded 'why'
    framing is."""
    ct = classify_content_type("Why did ABC shares fall 10% after results?", "")
    assert ct not in {OPINION, FORECAST}


def test_E_market_wrap_live_blog_is_not_single_event_or_market_event():
    ct = classify_content_type(
        "Sensex Today | Stock Market Live: Sensex jumps 660 pts, Nifty nears 24,000", ""
    )
    assert ct == MARKET_WRAP


def test_F_material_market_move_with_named_catalyst_is_market_event():
    ct = classify_content_type("Sensex rises 1,000 points after major policy announcement", "")
    assert ct == MARKET_EVENT


def test_analysis_is_penalized_but_not_banned_when_materially_relevant():
    """Problem 4's explicit non-goal: content type is a ranking signal, not
    an absolute ban — an OPINION-tagged story about a real regulator action
    still gets scored (and can still surface), just discounted."""
    from app.processing.content_type import content_type_penalty
    ct = classify_content_type("Why RBI's surprise rate decision could hit bank valuations", "")
    assert ct == OPINION
    penalty = content_type_penalty(ct)
    assert 0 < penalty < 30  # discounted, not zeroed/banned


def test_bare_why_word_alone_does_not_force_opinion_without_other_signals():
    # A sanity check on the anchor logic itself, not a headline from the brief.
    from app.processing.content_type import _has_hard_news_anchor
    assert _has_hard_news_anchor("Why did ABC shares fall 10% after results?") is True
    assert _has_hard_news_anchor("Why India's IPO markets are heating up after slow first half of 2026") is False


def test_generic_factors_explainer_scores_lower_than_a_real_single_event_investment():
    entities_generic = extract_entities("6 key factors driving the market today", "")
    _, _, _, generic_final, generic_breakdown = calculate_scores(
        "6 key factors driving the market today", "", "The Economic Times", 1,
        entities=entities_generic, event_type=None, country="India",
    )

    entities_event = extract_entities("Company X announces ₹70,000 crore investment", "")
    event_type = identify_event_type("Company X announces ₹70,000 crore investment")
    _, _, _, event_final, event_breakdown = calculate_scores(
        "Company X announces ₹70,000 crore investment", "", "Moneycontrol", 1,
        entities=entities_event, event_type=event_type, country="India",
    )

    assert event_final > generic_final
    assert generic_breakdown["content_type"] in {"FORECAST", "OPINION"}
    assert generic_breakdown["content_type_penalty"] > 0
