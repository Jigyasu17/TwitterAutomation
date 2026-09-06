"""
Source quality tiering.

Ranks *where a story came from*, independent of what it's about. A Tier 1
source (a regulator or exchange) can still publish a story with zero market
significance, and a Tier 3 source can still break something huge — this
module only answers "how much should we trust this publisher", not "is this
story important". Importance is calculated separately in classifier.py and
combines with this score rather than being replaced by it.

TIER 1 - Regulatory / official / primary sources (SEBI, RBI, NSE, BSE filings,
         official press releases, investor relations).
TIER 2 - Established financial/business media (Reuters, Bloomberg, Economic
         Times, Moneycontrol, Business Standard, Livemint, etc.)
TIER 3 - General business/tech media (TechCrunch, YourStory, Inc42, Forbes
         India, etc.)
TIER 4 - Unrecognized / low-quality aggregators / generic sources.
"""
from typing import Tuple

TIER_1_SOURCES = {
    "sebi", "rbi", "nse", "bse", "ministry of finance", "ministry of corporate affairs",
    "mca", "pib", "press information bureau", "sebi press release", "rbi press release",
    "investor relations", "official filing", "bseindia", "nseindia", "cbic", "cbdt",
    "income tax department", "irdai", "pfrda",
}

TIER_2_SOURCES = {
    "reuters", "bloomberg", "economic times", "moneycontrol", "business standard",
    "livemint", "mint", "financial times", "financial express", "cnbc-tv18",
    "cnbctv18", "bqprime", "bloombergquint", "ndtv profit", "the hindu businessline",
    "hindu businessline", "business line", "et now", "zee business", "wsj",
    "wall street journal", "the hindu", "indian express", "hindustan times business",
}

TIER_3_SOURCES = {
    "techcrunch", "yourstory", "inc42", "entrackr", "business today", "forbes india",
    "vccircle", "the ken", "morning context", "outlook business", "cnbc", "forbes",
    "reuters india", "ani", "pti", "press trust of india",
}

# Numeric quality score (0-100) associated with each tier — feeds into the
# research-confidence and confidence_score calculations. Kept in the same
# 0-100 space classifier.py already used so nothing downstream needs to change
# shape, only values.
TIER_SCORES = {1: 100, 2: 85, 3: 68, 4: 42}


def get_source_tier(source_name: str) -> int:
    """Returns 1-4 for a publisher name, matched case-insensitively/substring."""
    key = (source_name or "").strip().lower()
    if not key:
        return 4
    for name in TIER_1_SOURCES:
        if name in key:
            return 1
    for name in TIER_2_SOURCES:
        if name in key:
            return 2
    for name in TIER_3_SOURCES:
        if name in key:
            return 3
    return 4


def get_source_quality_score(source_name: str) -> int:
    """Returns the 0-100 trust score for a publisher name."""
    return TIER_SCORES[get_source_tier(source_name)]


def get_source_tier_and_score(source_name: str) -> Tuple[int, int]:
    tier = get_source_tier(source_name)
    return tier, TIER_SCORES[tier]


def build_legacy_source_priorities() -> dict:
    """
    Derives the flat {name: score} mapping that classifier.SOURCE_PRIORITIES
    has always exposed, so existing importers (source_discovery.py,
    drafts/builder.py's non-company-name guard) keep working unchanged while
    this module becomes the single source of truth for source trust.
    """
    mapping = {}
    for name in TIER_1_SOURCES:
        mapping[name] = TIER_SCORES[1]
    for name in TIER_2_SOURCES:
        mapping[name] = TIER_SCORES[2]
    for name in TIER_3_SOURCES:
        mapping[name] = TIER_SCORES[3]
    mapping["general"] = TIER_SCORES[4]
    return mapping
