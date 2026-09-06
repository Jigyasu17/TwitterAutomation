"""
Hook strategies.

Each function builds ONE candidate opening line from grounded evidence only
(story fields + confirmed research facts) and returns None if it doesn't
have enough to work with — it never invents a number, quote, or reaction to
fill the gap. app/drafts/engine.py calls whichever strategies
intelligence.potential_angles lists for the story's event type, drops the
Nones, and lets the quality scorer pick a winner among what's left.

This intentionally does NOT touch app/drafts/builder.py's existing
_hook_and_explainer — that function is the tested, working deterministic
baseline (app/drafts/engine.py always keeps it as a guaranteed-safe
fallback candidate). These are additional angles layered on top for stories
rich enough in research data to support more than one good post.
"""
import logging
from typing import List, Optional
from app.domain.models import StoryData
from app.drafts.builder import _format_amount, _resolve_company
from app.research.intelligence import StructuredIntelligence

logger = logging.getLogger(__name__)


_PERCENTAGE_FACT_TYPES = {"stock_movement", "subscription_number"}


def _format_fact_value(fact) -> str:
    """
    _format_amount() (builder.py) assumes a currency value — applying it to
    a percentage fact like stock_movement produces nonsense (e.g. a 8.0%
    move rendered as "₹8"). Route by fact type/unit instead. Shared with
    app/drafts/engine.py, which imports this rather than duplicating it.
    """
    if fact.fact_type in _PERCENTAGE_FACT_TYPES or fact.unit == "percentage":
        try:
            val = float(fact.normalized_value)
            suffix = "x" if fact.fact_type == "subscription_number" else "%"
            return f"{abs(val):.1f}{suffix}"
        except (TypeError, ValueError):
            return fact.original_value
    return _format_amount(fact)


def _company(intel: StructuredIntelligence, story: StoryData) -> str:
    resolved = _resolve_company(story)
    return resolved or "This company"


def _primary_number_fact(intel: StructuredIntelligence):
    return intel.confirmed_facts[0] if intel.confirmed_facts else None


def number_led(story: StoryData, intel: StructuredIntelligence) -> Optional[str]:
    fact = _primary_number_fact(intel)
    if not fact or fact.fact_type in _PERCENTAGE_FACT_TYPES:
        return None  # percentage moves read better through contrast/data_led, not "X%. That's the figure..."
    amount = _format_fact_value(fact)
    company = _company(intel, story)
    label = fact.fact_type.replace("_", " ")
    return f"{amount}. That's the {label.replace('amount', '').strip()} figure {company} just put on the board."


def consequence(story: StoryData, intel: StructuredIntelligence) -> Optional[str]:
    company = _company(intel, story)
    if intel.market_impact == "negative":
        return f"This could change how investors look at {company} next quarter."
    if intel.market_impact == "positive":
        return f"This could reshape {company}'s next growth phase."
    return None


def contrast(story: StoryData, intel: StructuredIntelligence) -> Optional[str]:
    fact = None
    for f in intel.confirmed_facts:
        if f.fact_type == "stock_movement":
            fact = f
            break
    if not fact or not isinstance(fact.normalized_value, (int, float)):
        return None
    company = _company(intel, story)
    pct = abs(fact.normalized_value)
    direction = "jumped" if fact.normalized_value >= 0 else "fell"
    return f"{company} stock {direction} {pct:.1f}% today. But the real story is what's underneath it →"


def curiosity(story: StoryData, intel: StructuredIntelligence) -> Optional[str]:
    if not intel.confirmed_facts:
        return None
    company = _company(intel, story)
    return f"There's one number in {company}'s update most headlines are missing."


def investor_angle(story: StoryData, intel: StructuredIntelligence) -> Optional[str]:
    company = _company(intel, story)
    if intel.event_type not in {"FUNDING", "IPO_FILING", "IPO_ANNOUNCEMENT", "IPO_PRICING", "INVESTMENT"}:
        return None
    return f"Why are investors suddenly paying attention to {company}?"


def breaking(story: StoryData, intel: StructuredIntelligence) -> Optional[str]:
    company = _company(intel, story)
    if intel.event_type in {"IPO_LISTING", "REGULATORY_ACTION"}:
        return f"{company} just made a move that could reshape what comes next."
    return None


def data_led(story: StoryData, intel: StructuredIntelligence) -> Optional[str]:
    if len(intel.confirmed_facts) < 2:
        return None
    primary, secondary = intel.confirmed_facts[0], intel.confirmed_facts[1]
    p_label = primary.fact_type.replace("_", " ")
    s_label = secondary.fact_type.replace("_", " ")
    return f"{p_label.title()} isn't the biggest surprise here. {s_label.title()} is."


def question(story: StoryData, intel: StructuredIntelligence) -> Optional[str]:
    company = _company(intel, story)
    if company == "This company":
        return None
    return f"Is {company} turning a corner, or is this a one-off?"


def second_order(story: StoryData, intel: StructuredIntelligence) -> Optional[str]:
    if intel.event_type not in {"ACQUISITION", "MERGER", "STOCK_MOVEMENT", "POLICY_CHANGE"}:
        return None
    return "The immediate reaction is obvious. The second-order effect is more interesting."


def surprise(story: StoryData, intel: StructuredIntelligence) -> Optional[str]:
    fact = _primary_number_fact(intel)
    if not fact or intel.source_confidence_label not in {"HIGH", "MEDIUM"}:
        return None
    company = _company(intel, story)
    return f"Nobody expected this number from {company}."


HOOK_STRATEGIES = {
    "number_led": number_led,
    "consequence": consequence,
    "contrast": contrast,
    "curiosity": curiosity,
    "investor_angle": investor_angle,
    "breaking": breaking,
    "data_led": data_led,
    "question": question,
    "second_order": second_order,
    "surprise": surprise,
}


def generate_hook_candidates(story: StoryData, intel: StructuredIntelligence) -> List[tuple]:
    """Returns [(strategy_name, hook_text), ...] for every strategy that produced grounded text."""
    out = []
    for name in intel.potential_angles:
        fn = HOOK_STRATEGIES.get(name)
        if not fn:
            continue
        text = fn(story, intel)
        if text:
            out.append((name, text))
    return out
