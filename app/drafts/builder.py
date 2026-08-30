import logging
from typing import List, Optional, Tuple
from app.domain.models import StoryData, ResearchFactData

logger = logging.getLogger(__name__)

TWEET_LIMIT = 280

NUMERIC_FACT_TYPES = {
    "funding_amount", "valuation", "acquisition_value", "ipo_size", "revenue", "profit", "loss"
}


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


def _hook_line(story: StoryData, facts: List[ResearchFactData]) -> Tuple[str, Optional[ResearchFactData]]:
    """Builds the primary tweet line for a story. Returns (text, fact_used_if_any)."""
    company = story.company or "The company"
    event = story.event_type or "OTHER"

    if event == "FUNDING":
        fact = _find_fact(facts, "funding_amount")
        if fact:
            return f"\U0001F6A8 {company} raises {_format_amount(fact)} in fresh funding", fact
        return f"\U0001F6A8 {company} raises fresh funding", None

    if event == "ACQUISITION":
        fact = _find_fact(facts, "acquisition_value")
        if fact:
            return f"\U0001F91D {company} acquires a company for {_format_amount(fact)}", fact
        return f"\U0001F91D {company} announces an acquisition", None

    if event in {"IPO_FILING", "IPO_ANNOUNCEMENT"}:
        fact = _find_fact(facts, "ipo_size")
        if fact:
            return f"\U0001F4C8 {company} files for IPO to raise {_format_amount(fact)}", fact
        return f"\U0001F4C8 {company} files for IPO", None

    if event == "IPO_LISTING":
        return f"\U0001F514 {company} debuts on the stock exchange today", None

    if event == "STOCK_MOVEMENT":
        fact = _find_fact(facts, "stock_movement")
        if fact and isinstance(fact.normalized_value, (int, float)):
            direction = "jumps" if fact.normalized_value >= 0 else "falls"
            pct = abs(fact.normalized_value)
            return f"\U0001F4CA {company} shares {direction} {pct:.1f}%", fact
        return f"\U0001F4CA {company} shares in focus", None

    if event in {"PROFIT_UPDATE", "REVENUE_UPDATE", "EARNINGS"}:
        fact = _find_fact(facts, "profit") or _find_fact(facts, "revenue")
        if fact:
            label = "profit" if fact.fact_type == "profit" else "revenue"
            return f"\U0001F4B0 {company} reports {label} of {_format_amount(fact)}", fact
        return f"\U0001F4B0 {company} reports quarterly results", None

    if event == "REGULATORY_ACTION":
        return f"⚠️ Regulatory action: {company}", None

    if event == "LAYOFF":
        return f"\U0001F4C9 {company} announces layoffs", None

    # No specific template for this event type — fall back to the title itself
    return story.title, None


def generate_post_text(story: StoryData) -> Tuple[str, Optional[List[str]], str, str]:
    """
    Builds tweet-ready content from a story and its research report (if any),
    using deterministic rule-based templates — no external API calls.

    Returns (post_text, thread_json, image_headline, image_subheadline).
    """
    report = story.research_report
    facts = report.facts if report else []

    hook, used_fact = _hook_line(story, facts)
    post_text = _truncate(hook)

    thread: List[str] = []

    if report and report.why_it_matters:
        thread.append(_truncate(f"Why it matters: {report.why_it_matters}"))

    other_facts = [
        f for f in facts
        if f.fact_type in NUMERIC_FACT_TYPES and f is not used_fact
    ][:2]
    if other_facts:
        parts = [f"{f.fact_type.replace('_', ' ').title()}: {_format_amount(f)}" for f in other_facts]
        thread.append(_truncate(" | ".join(parts)))

    if story.article_url:
        thread.append(_truncate(f"Source: {story.article_url}"))

    image_headline = _truncate(story.company or story.title, 60)
    image_subheadline = _truncate(story.category or "", 60)

    return post_text, (thread or None), image_headline, image_subheadline
