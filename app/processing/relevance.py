"""
Indian market/business relevance gate.

MarketPulse's audience cares about Indian markets specifically. A story can
be well-sourced and even materially important somewhere in the world and
still be a poor fit for this feed if it has no connection to Indian
companies, regulators, exchanges, or macro conditions that move Indian
markets. This module scores that connection on its own axis, separate from
"is this important" (classifier.calculate_scores) and "is this real news"
(noise_filter.py) — the three combine, they don't replace each other.
"""
import re
from typing import Any, Dict

# Regulators, exchanges, and government bodies whose mention is an
# unambiguous, direct India signal.
INDIA_CORE_SIGNALS = [
    "rbi", "sebi", "nse", "bse", "sensex", "nifty", "gst", "cbic", "cbdt",
    "ministry of finance", "niti aayog", "sebi bars", "rbi imposes",
    "reserve bank of india", "securities and exchange board",
]

# Currency/unit tells that the story is denominated in Indian terms.
INDIA_CURRENCY_SIGNALS = ["crore", "cr", "lakh", "₹", "rupee", "rupees", "inr"]

# Global macro topics that matter to Indian markets indirectly (oil prices,
# Fed policy, global demand shocks) — these get partial credit, not full
# credit, since they're relevant but not India-specific.
GLOBAL_MACRO_WITH_INDIA_IMPACT = [
    "fed rate", "federal reserve", "us inflation", "us fed", "opec", "crude oil",
    "brent crude", "china economy", "global oil", "eurozone", "dollar index",
    "us treasury yield", "global recession", "commodity prices", "global markets",
]

INDIAN_CITIES = [
    "mumbai", "delhi", "bengaluru", "bangalore", "hyderabad", "chennai",
    "kolkata", "pune", "ahmedabad", "gurugram", "gurgaon", "noida",
]


def calculate_india_relevance(
    title: str,
    summary: str,
    entities: Dict[str, Any],
    country: str = None,
) -> int:
    """
    Returns an India-relevance score from 0-100.

    100 = direct India regulatory/exchange/company story.
    ~55-70 = global macro story with clear knock-on effect on Indian markets.
    ~15-30 = generic international business news with no India link.
    """
    text = f"{title or ''} {summary or ''}".lower()

    score = 0

    # 1. Explicit country tag from the collector/classifier.
    if country and "india" in country.lower():
        score += 35

    # 2. Regulator/exchange core signals — the strongest possible tell.
    if any(sig in text for sig in INDIA_CORE_SIGNALS):
        score += 45

    # 3. Currency denomination.
    if any(re.search(r'\b' + re.escape(sig) + r'\b', text) for sig in INDIA_CURRENCY_SIGNALS):
        score += 15

    # 4. Indian cities mentioned.
    if any(city in text for city in INDIAN_CITIES):
        score += 10

    # 5. Extracted entities: Indian companies or "India"/Indian-city countries.
    companies = [c.lower() for c in (entities or {}).get("Companies", [])]
    countries = [c.lower() for c in (entities or {}).get("Countries", [])]
    if companies:
        score += 20
    if any("india" in c for c in countries):
        score += 15

    # 6. Global macro with indirect India impact — partial credit only,
    # and only if nothing more direct already fired.
    if score == 0 and any(sig in text for sig in GLOBAL_MACRO_WITH_INDIA_IMPACT):
        score = 55

    return max(0, min(100, score))


def relevance_multiplier(relevance_score: int) -> float:
    """
    Maps an India-relevance score to a multiplier applied to importance.
    A strongly India-relevant story gets a mild boost; a story with no
    India link at all is scaled down substantially without being zeroed
    out outright (a source-quality/materiality signal can still keep it
    visible at low priority rather than silently vanishing).
    """
    if relevance_score >= 70:
        return 1.15
    if relevance_score >= 45:
        return 1.0
    if relevance_score >= 25:
        return 0.8
    return 0.6
