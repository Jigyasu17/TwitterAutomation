"""
Staleness / actionability decay.

classifier.py's freshness bonus only ever adds up to 10 points for
recent stories — it never subtracts anything for very old ones, so a
290-day-old story with decent fundamentals sits at the same baseline score
forever. This module is the missing other half: a smooth, explainable
multiplier applied to importance_score based on age, with a softer curve
for event types whose news cycle genuinely spans weeks (an IPO process, an
ongoing regulatory investigation) rather than resolving in a day.
"""
from datetime import datetime
from typing import Optional

# Event types whose real-world news cycle can legitimately span weeks —
# an IPO filed 3 weeks ago is still "in process," unlike a stock move or a
# single earnings beat, which is stale news within days.
LONG_CYCLE_EVENT_TYPES = {
    "IPO_FILING", "IPO_ANNOUNCEMENT", "IPO_PRICING", "IPO_LISTING",
    "ACQUISITION", "MERGER", "REGULATORY_ACTION",
}

ONGOING_KEYWORDS = [
    "ongoing", "probe", "investigation", "pending", "in progress",
    "continues", "continuing", "still under", "yet to",
]


def is_ongoing_event(event_type: Optional[str], title: str = "", summary: str = "") -> bool:
    """True for stories whose news cycle plausibly still spans weeks."""
    if event_type in LONG_CYCLE_EVENT_TYPES:
        return True
    text = f"{title or ''} {summary or ''}".lower()
    return any(k in text for k in ONGOING_KEYWORDS)


def staleness_multiplier(
    published_at: Optional[datetime],
    event_type: Optional[str] = None,
    title: str = "",
    summary: str = "",
    now: Optional[datetime] = None,
) -> float:
    """
    Returns a 0.0-1.0 multiplier applied to importance_score.

    Curve (short-cycle stories):
        0-6h:    1.00  (fully actionable)
        6-24h:   0.95  (very relevant)
        1-2d:    0.85  (relevant)
        2-7d:    0.65  (lower priority)
        7-30d:   0.35  (strong decay)
        30-90d:  0.15
        90d+:    0.05  (effectively historical)

    Ongoing/long-cycle stories (see is_ongoing_event) get a materially
    softer curve, floored at 0.5 through 30 days and 0.25 beyond that —
    still decaying so nothing is exempt forever, just more slowly.

    published_at=None returns 1.0 (neutral — matches the pre-existing
    behavior for callers that don't pass a timestamp, same convention as
    classifier._freshness_bonus).
    """
    if not published_at:
        return 1.0

    reference = now or datetime.utcnow()
    try:
        pub = published_at.replace(tzinfo=None) if getattr(published_at, "tzinfo", None) else published_at
        hours_ago = (reference - pub).total_seconds() / 3600.0
    except Exception:
        return 1.0

    if hours_ago < 0:
        hours_ago = 0

    ongoing = is_ongoing_event(event_type, title, summary)
    days_ago = hours_ago / 24.0

    if hours_ago <= 6:
        return 1.0
    if hours_ago <= 24:
        return 0.95
    if days_ago <= 2:
        return 0.85
    if days_ago <= 7:
        return 0.65
    if days_ago <= 30:
        return 0.5 if ongoing else 0.35
    if days_ago <= 90:
        return 0.25 if ongoing else 0.15
    return 0.10 if ongoing else 0.05
