"""
Canonical entity-role classification — the single source of truth for
"which extracted names are never a company," used consistently by entity
extraction, company resolution, deduplication, and drafting.

Before this module existed, three different modules independently guessed at
this (classifier.KNOWN_COMPANIES included "reuters"/"bloomberg"/"sebi"/"rbi"
as if they were companies; drafts/builder.py derived its own exclusion list
from SOURCE_PRIORITIES; deduplication.py hardcoded a third, narrower list).
That's exactly the "several conflicting lists" this module replaces.

Roles:
- REGULATORS: government/regulatory bodies. Can be a legitimate entity a
  story is ABOUT (e.g. "SEBI warns investors...") but never the subject
  COMPANY of an event (SEBI doesn't IPO, doesn't get acquired).
- WIRE_SERVICES_AND_PUBLISHERS: news wire services and publications that
  show up in text (bylines, "— Reuters" RSS summary suffixes) but are never
  themselves the company a MarketPulse story is about.
- EXCHANGES_ELIGIBLE_AS_COMPANY: NSE/BSE are stock exchanges, which *can*
  legitimately be the company a story is about (e.g. NSE's own IPO) — they
  are deliberately NOT in NON_COMPANY_ENTITIES.
"""
from typing import Iterable, List

REGULATORS = {
    "sebi", "rbi", "irdai", "pfrda", "mca", "cbic", "cbdt",
    "ministry of finance", "ministry of corporate affairs",
    "reserve bank of india", "securities and exchange board",
    "securities and exchange board of india",
}

WIRE_SERVICES_AND_PUBLISHERS = {
    "reuters", "bloomberg", "bloomberg.com", "pti", "press trust of india", "ani",
    "moneycontrol", "moneycontrol.com", "livemint", "mint", "economic times",
    "the economic times", "business standard", "financial times", "financial express",
    "techcrunch", "yourstory", "tradingview", "linkedin", "cnbc", "cnbc-tv18",
    "cnbctv18", "bqprime", "bloombergquint", "ndtv profit", "the hindu businessline",
    "hindu businessline", "business line", "et now", "zee business", "wsj",
    "wall street journal", "the hindu", "indian express", "the indian express",
    "hindustan times", "forbes", "forbes india", "vccircle", "the ken",
    "morning context", "outlook business", "inc42", "entrackr", "business today",
    "rediff", "ndtv", "theprint", "times of india", "the times of india", "upstox",
}

# Stock exchanges: deliberately NOT included above — they can be a story's
# actual subject (e.g. "NSE gets regulatory nod for its own Rs 30,000cr IPO").
EXCHANGES_ELIGIBLE_AS_COMPANY = {"nse", "bse"}

NON_COMPANY_ENTITIES = REGULATORS | WIRE_SERVICES_AND_PUBLISHERS


def is_non_company(name: str) -> bool:
    return (name or "").strip().lower() in NON_COMPANY_ENTITIES


def is_regulator(name: str) -> bool:
    return (name or "").strip().lower() in REGULATORS


def filter_non_company_entities(names: Iterable[str]) -> List[str]:
    """Drops any name that's a known regulator/wire-service/publisher, case-insensitively."""
    return [n for n in names if not is_non_company(n)]
