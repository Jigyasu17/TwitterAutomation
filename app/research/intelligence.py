"""
Structured intelligence layer.

The research engine already extracts facts, cross-checks them, and detects
conflicts (fact_extractor.py / verifier.py) — but that output only ever
became a markdown report for human reading (report_builder.py). Nothing
downstream consumed the *structured* signal (which facts are confirmed vs.
disputed, whether the story reads as positive/negative for the company,
which angle a tweet should take). This module compiles that signal into one
object so app/drafts/hooks.py can build angles grounded in research instead
of re-deriving everything from the raw title.

No new persistence: this is computed on the fly from a StoryData + its
already-loaded research_report, exactly the same way drafts/builder.py
already reads story.research_report.facts today. Keeping it stateless avoids
a schema/migration change for something purely derived.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from app.domain.models import StoryData, ResearchFactData, ResearchConflictData
from app.processing.classifier import SOURCE_PRIORITIES
from app.research.fact_extractor import extract_facts_from_text

logger = logging.getLogger(__name__)

NUMERIC_FACT_TYPES = {
    "funding_amount", "valuation", "acquisition_value", "ipo_size", "revenue",
    "profit", "loss", "stock_movement", "subscription_number",
}

# Event types where the "market impact" direction is unambiguously negative
# for the company even without a numeric fact to check the sign of.
NEGATIVE_EVENT_TYPES = {"LAYOFF", "REGULATORY_ACTION", "LEGAL"}
POSITIVE_EVENT_TYPES = {
    "FUNDING", "IPO_LISTING", "PARTNERSHIP", "PRODUCT_LAUNCH", "EXPANSION",
}

# Which hook strategies (app/drafts/hooks.py) make sense to attempt for a
# given event type. Kept here (not in hooks.py) because it's a property of
# what evidence an event type typically has available, which is research
# territory, not copywriting territory.
ANGLE_MAP = {
    "FUNDING": ["number_led", "consequence", "investor_angle", "explainer"],
    "ACQUISITION": ["consequence", "second_order", "number_led", "explainer"],
    "MERGER": ["consequence", "second_order", "explainer"],
    "IPO_FILING": ["number_led", "curiosity", "investor_angle"],
    "IPO_ANNOUNCEMENT": ["number_led", "curiosity", "investor_angle"],
    "IPO_PRICING": ["number_led", "data_led", "investor_angle"],
    "IPO_LISTING": ["breaking", "question", "investor_angle"],
    "STOCK_MOVEMENT": ["contrast", "data_led", "second_order"],
    "PROFIT_UPDATE": ["contrast", "data_led", "surprise"],
    "REVENUE_UPDATE": ["data_led", "contrast", "explainer"],
    "EARNINGS": ["data_led", "contrast", "surprise"],
    "REGULATORY_ACTION": ["consequence", "breaking", "explainer"],
    "LAYOFF": ["consequence", "data_led", "explainer"],
    "INVESTMENT": ["number_led", "consequence", "investor_angle"],
    "EXPANSION": ["consequence", "explainer"],
    "POLICY_CHANGE": ["consequence", "explainer", "second_order"],
    "PARTNERSHIP": ["explainer", "consequence"],
    "PRODUCT_LAUNCH": ["curiosity", "explainer"],
    "LEADERSHIP_CHANGE": ["consequence", "explainer"],
    "LEGAL": ["consequence", "breaking"],
}
DEFAULT_ANGLES = ["explainer", "question"]


@dataclass
class StructuredIntelligence:
    event_type: str
    company: Optional[str]
    why_it_matters: Optional[str]
    key_numbers: List[ResearchFactData] = field(default_factory=list)
    companies: List[str] = field(default_factory=list)
    people: List[str] = field(default_factory=list)
    market_impact: str = "neutral"  # "positive" | "negative" | "neutral"
    investor_angle: Optional[str] = None
    confirmed_facts: List[ResearchFactData] = field(default_factory=list)
    disputed_fact_types: List[str] = field(default_factory=list)
    source_confidence_label: str = "UNCONFIRMED"
    source_confidence_score: int = 0
    has_research: bool = False
    potential_angles: List[str] = field(default_factory=list)


def _market_impact_label(event_type: str, facts: List[ResearchFactData]) -> str:
    for f in facts:
        if f.fact_type == "stock_movement" and isinstance(f.normalized_value, (int, float)):
            return "positive" if f.normalized_value >= 0 else "negative"
        if f.fact_type in {"profit", "revenue"} and isinstance(f.normalized_value, (int, float)):
            return "positive"
        if f.fact_type == "loss":
            return "negative"
    if event_type in NEGATIVE_EVENT_TYPES:
        return "negative"
    if event_type in POSITIVE_EVENT_TYPES:
        return "positive"
    return "neutral"


def _confidence_label(score: int) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    if score > 0:
        return "LOW"
    return "UNCONFIRMED"


def build_structured_intelligence(story: StoryData) -> StructuredIntelligence:
    """Compiles everything the drafting system needs from a story + its research report, if any."""
    event_type = story.event_type or "OTHER"
    report = story.research_report
    entities = story.entities or {}

    facts: List[ResearchFactData] = list(report.facts) if report else []
    conflicts: List[ResearchConflictData] = list(report.conflicts) if report else []
    confidence_score = report.confidence_score if report else 0

    key_numbers = [f for f in facts if f.fact_type in NUMERIC_FACT_TYPES]

    # Headline-level fallback: article-body fact extraction depends on
    # resolving a real article URL, which every currently-configured source
    # is a Google News redirect wrapper for (see docs/vercel_compatibility.md
    # and drafts/builder.py's _source_line comment) — extraction routinely
    # comes back empty even when the headline itself states a clear number
    # ("InstaAstro raises $12 million", "Infosys Shares Jump 5%"). Rather
    # than draft around a number that's sitting in plain sight, run the same
    # regex-based extractor the research pipeline already uses on the
    # headline/summary text directly. This isn't invention — the figure came
    # from the story's own published headline, the same text a human reader
    # already sees — just marked at reduced confidence since it isn't
    # cross-source-verified the way a researched fact is.
    if not key_numbers:
        headline_facts = extract_facts_from_text(f"{story.title} {story.summary or ''}")
        for f in headline_facts:
            f.confidence = min(f.confidence, 0.6)
        key_numbers = [f for f in headline_facts if f.fact_type in NUMERIC_FACT_TYPES]

    disputed_types = {c.fact_type for c in conflicts if c.status == "OPEN"}
    confirmed_facts = [f for f in key_numbers if f.fact_type not in disputed_types]

    angles = ANGLE_MAP.get(event_type, DEFAULT_ANGLES)
    # A story with no grounding facts at all can't sustain data-driven angles
    # (number_led, data_led) without inventing numbers — drop those so the
    # fact-safety rule in hooks.py never gets tempted.
    if not confirmed_facts:
        angles = [a for a in angles if a not in {"number_led", "data_led"}] or DEFAULT_ANGLES

    return StructuredIntelligence(
        event_type=event_type,
        company=story.company,
        why_it_matters=report.why_it_matters if report else None,
        key_numbers=key_numbers,
        companies=entities.get("Companies", []),
        people=entities.get("People", []),
        market_impact=_market_impact_label(event_type, facts),
        investor_angle=report.why_it_matters if report else None,
        confirmed_facts=confirmed_facts,
        disputed_fact_types=sorted(disputed_types),
        source_confidence_label=_confidence_label(confidence_score),
        source_confidence_score=confidence_score,
        has_research=report is not None and report.status in {"COMPLETED", "NEEDS_REVIEW"},
        potential_angles=angles,
    )
