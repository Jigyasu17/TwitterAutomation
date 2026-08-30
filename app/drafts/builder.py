import logging
from typing import List, Optional, Tuple
from app.domain.models import StoryData, ResearchFactData
from app.processing.classifier import SOURCE_PRIORITIES

logger = logging.getLogger(__name__)

TWEET_LIMIT = 280

NUMERIC_FACT_TYPES = {
    "funding_amount", "valuation", "acquisition_value", "ipo_size", "revenue", "profit", "loss"
}

# Wire services, regulators, and publications that get cited inside article
# text often get mistakenly extracted by the classifier as "the company" the
# story is about (e.g. a story mentioning "...according to Reuters..." can
# come out with company="Reuters"). Reuses the same name list classifier.py
# already maintains for source-trust scoring, since it's exactly the set of
# names that show up as citations rather than story subjects.
_NON_COMPANY_NAMES = {k for k in SOURCE_PRIORITIES if k != "general"}


def _resolve_company(story: StoryData) -> Optional[str]:
    """
    Returns story.company, unless it's actually a wire service/regulator/
    publication name — guards against embarrassingly wrong-sounding hooks
    like "SEBI just hit the stock market!" (SEBI is India's securities
    regulator, not a listed company).
    """
    company = story.company
    if not company or company.strip().lower() in _NON_COMPANY_NAMES:
        return None
    return company


def _find_fact(facts: List[ResearchFactData], fact_type: str) -> Optional[ResearchFactData]:
    for f in facts:
        if f.fact_type == fact_type:
            return f
    return None


def _format_amount(fact: ResearchFactData) -> str:
    """Formats a normalized monetary fact value into a short human-readable string."""
    try:
        val = float(fact.normalized_value)
    except (TypeError, ValueError):
        return fact.original_value

    currency = fact.currency or "INR"
    symbol = "$" if currency == "USD" else "₹"

    if currency == "INR" and val >= 10_000_000:
        return f"{symbol}{val / 10_000_000:.1f}Cr"
    if val >= 1_000_000_000:
        return f"{symbol}{val / 1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"{symbol}{val / 1_000_000:.1f}M"
    return f"{symbol}{val:,.0f}"


def _truncate(text: str, limit: int = TWEET_LIMIT) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


GOOGLE_NEWS_HOST = "news.google.com"


def _source_line(story: StoryData) -> Optional[str]:
    """
    Google News RSS links are obfuscated redirect wrappers — the real article
    URL only resolves through an unofficial, fragile decoding step (Google
    dropped plain HTTP redirects for these), so showing one as a "clickable"
    link in a tweet is both ugly and unreliable. For those, show the outlet
    name instead of a link. Direct RSS sources (e.g. TechCrunch) already give
    the real article URL, so those stay as an actual clickable link.
    """
    if not story.article_url:
        return None
    if GOOGLE_NEWS_HOST in story.article_url:
        return f"Source: {story.source_name}" if story.source_name else None
    return f"Source: {story.article_url}"


def _hook_and_explainer(
    story: StoryData, facts: List[ResearchFactData]
) -> Tuple[str, Optional[ResearchFactData], Optional[str]]:
    """
    Builds a retention hook (the attention-grabbing opening line) and a plain-
    language, jargon-free one-liner explaining why it matters, for a story.

    Deliberately NOT reusing report_builder.generate_why_it_matters() — that
    text is written for the internal analyst-facing research report ("capital
    infusion", "immediate runway") and is the opposite of the plain, simple
    wording a tweet needs.

    Returns (hook, fact_used_if_any, plain_explainer_or_none).
    """
    company = _resolve_company(story) or "This company"
    event = story.event_type or "OTHER"

    if event == "FUNDING":
        fact = _find_fact(facts, "funding_amount")
        if fact:
            hook = f"\U0001F4B0 {company} just landed {_format_amount(fact)} in funding!"
        else:
            hook = f"\U0001F4B0 {company} just landed fresh funding!"
        explainer = "That's fresh cash to grow faster, hire more people, and expand."
        return hook, fact, explainer

    if event == "ACQUISITION":
        fact = _find_fact(facts, "acquisition_value")
        if fact:
            hook = f"\U0001F91D Big deal: {company} is buying another company for {_format_amount(fact)}."
        else:
            hook = f"\U0001F91D Big deal: {company} just acquired another company."
        explainer = "One company is taking over another — expect changes ahead."
        return hook, fact, explainer

    if event in {"IPO_FILING", "IPO_ANNOUNCEMENT"}:
        fact = _find_fact(facts, "ipo_size")
        if fact:
            hook = f"\U0001F4C8 {company} is going public! Filing to raise {_format_amount(fact)}."
        else:
            hook = f"\U0001F4C8 {company} is going public!"
        explainer = f"Soon, regular investors will be able to buy a piece of {company} on the stock market."
        return hook, fact, explainer

    if event == "IPO_LISTING":
        hook = f"\U0001F514 Big day: {company} just hit the stock market!"
        explainer = f"You can now buy or sell {company} shares like any other stock."
        return hook, None, explainer

    if event == "STOCK_MOVEMENT":
        fact = _find_fact(facts, "stock_movement")
        if fact and isinstance(fact.normalized_value, (int, float)):
            pct = abs(fact.normalized_value)
            if fact.normalized_value >= 0:
                hook = f"\U0001F4C8 {company} stock is on fire — up {pct:.1f}% today!"
                explainer = f"Investors are feeling good about {company} right now."
            else:
                hook = f"\U0001F4C9 {company} stock just dropped {pct:.1f}%."
                explainer = f"Investors are worried about {company} right now."
            return hook, fact, explainer
        return f"\U0001F4CA {company} shares are in focus today.", None, None

    if event in {"PROFIT_UPDATE", "REVENUE_UPDATE", "EARNINGS"}:
        fact = _find_fact(facts, "profit") or _find_fact(facts, "revenue")
        if fact:
            label = "profit" if fact.fact_type == "profit" else "revenue"
            hook = f"\U0001F4B0 {company}'s results are in — {label} of {_format_amount(fact)}."
        else:
            hook = f"\U0001F4B0 {company} just reported its latest results."
        explainer = f"This shows how {company} is actually doing financially."
        return hook, fact, explainer

    if event == "REGULATORY_ACTION":
        hook = f"⚠️ {company} just got in trouble with regulators."
        explainer = "That usually means rules were broken — a fine or restrictions could follow."
        return hook, None, explainer

    if event == "LAYOFF":
        hook = f"\U0001F4C9 {company} is cutting jobs."
        explainer = "A sign the company is trying to cut costs and tighten its belt."
        return hook, None, explainer

    # No specific template for this event type — still add a light hook cue
    # rather than dropping the raw headline in unchanged.
    return f"\U0001F4F0 {story.title}", None, None


def generate_post_text(story: StoryData) -> Tuple[str, Optional[List[str]], str, str]:
    """
    Builds tweet-ready content from a story and its research report (if any),
    using deterministic rule-based templates — no external API calls.

    Leads with a retention hook, then a plain-language explanation of why it
    matters, combined into a single tweet when it fits (most readers never
    open a thread); overflow and supporting numbers go into thread_json.

    Returns (post_text, thread_json, image_headline, image_subheadline).
    """
    report = story.research_report
    facts = report.facts if report else []

    hook, used_fact, explainer = _hook_and_explainer(story, facts)

    combined = f"{hook} {explainer}" if explainer else hook
    thread: List[str] = []
    if len(combined) <= TWEET_LIMIT:
        post_text = _truncate(combined)
    else:
        post_text = _truncate(hook)
        if explainer:
            thread.append(_truncate(explainer))

    other_facts = [
        f for f in facts
        if f.fact_type in NUMERIC_FACT_TYPES and f is not used_fact
    ][:2]
    if other_facts:
        parts = [f"{f.fact_type.replace('_', ' ').title()}: {_format_amount(f)}" for f in other_facts]
        thread.append(_truncate(" | ".join(parts)))

    source_line = _source_line(story)
    if source_line:
        thread.append(_truncate(source_line))

    image_headline = _truncate(story.company or story.title, 60)
    image_subheadline = _truncate(story.category or "", 60)

    return post_text, (thread or None), image_headline, image_subheadline
