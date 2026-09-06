"""
Noise filtering layer.

Rejects/down-ranks the class of article that is technically "news" but adds
no signal: listicles ("5 stocks to watch"), generic market-outlook filler,
motivational founder profiles, and routine non-events (a CEO attending a
conference, a minor award). None of these signals are used alone — a
listicle-shaped title with a genuinely material number in it (e.g. a
regulatory fine amount) should NOT be nuked just because it also says "top
5". Combination of title/summary phrasing + presence of a material event
type + presence of extracted numbers/entities decides the verdict, per the
project brief's explicit instruction not to rely on keyword filtering alone.
"""
import re
from typing import Any, Dict, List, Tuple

# Patterns that are near-certain noise-listicle/filler shapes.
LISTICLE_PATTERNS = [
    r'^\s*\d+\s+(stocks|shares|things|reasons|ways|tips|charts)\b',
    r'\btop\s+\d+\b',
    r'\bstocks?\s+to\s+watch\b',
    r'\bthings?\s+(investors|traders)\s+should\s+know\b',
    r'\bmay\s+rise\b.*\btoday\b',
    r'\b\d+\s+stocks?\s+that\s+(could|may|might)\b',
]

# Generic outlook/opinion filler that carries no new information.
GENERIC_FILLER_PATTERNS = [
    r'\bmarket\s+experts?\s+say\b',
    r'\bgeneric\s+market\s+outlook\b',
    r'\bwhat\s+to\s+expect\s+(today|this\s+week)\b',
    r'\banalysts?\s+(believe|expect|predict)\b.*\boutlook\b',
]

# Motivational / fluff / non-material corporate PR.
FLUFF_PATTERNS = [
    r'\bhis\s+(inspiring\s+)?journey\b',
    r'\bhow\s+he\s+built\b',
    r'\bhow\s+she\s+built\b',
    r'\bsuccess\s+story\b',
    r'\battends?\s+(the\s+)?(event|summit|conference|gala)\b',
    r'\bwins?\s+(an?\s+)?(award|recognition)\b',
    r'\bfelicitated\b',
    r'\bmotivational\b',
    r'\binspirational\b',
]

MATERIAL_EVENT_TYPES = {
    "FUNDING", "ACQUISITION", "MERGER", "IPO_FILING", "IPO_PRICING", "IPO_LISTING",
    "IPO_ANNOUNCEMENT", "EARNINGS", "PROFIT_UPDATE", "REVENUE_UPDATE",
    "STOCK_MOVEMENT", "REGULATORY_ACTION", "LAYOFF", "INVESTMENT", "EXPANSION",
    "POLICY_CHANGE",
}

NUMBER_PATTERN = re.compile(r'(\d+(?:\.\d+)?\s*%|[$₹]\s*\d|\brs\.?\s*\d|\bcrore\b|\bcr\b|\bbillion\b|\bmillion\b|\blakh\b)', re.I)


def _matches_any(patterns: List[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def detect_noise(
    title: str,
    summary: str,
    entities: Dict[str, Any] = None,
    event_type: str = None,
    has_numeric_facts: bool = False,
) -> Tuple[bool, int, List[str]]:
    """
    Returns (is_noise, noise_penalty_points, reasons).

    noise_penalty_points is subtracted from importance/postability in
    classifier.calculate_scores; it is not itself a hard reject — a listicle
    title wrapped around a genuinely material regulatory fine still keeps
    enough of its importance score to surface, just discounted.
    """
    text = f"{title or ''} {summary or ''}"
    reasons: List[str] = []

    has_material_event = bool(event_type) and event_type in MATERIAL_EVENT_TYPES
    has_company = bool((entities or {}).get("Companies"))
    has_numbers = has_numeric_facts or bool(NUMBER_PATTERN.search(text))

    is_listicle = _matches_any(LISTICLE_PATTERNS, text)
    is_filler = _matches_any(GENERIC_FILLER_PATTERNS, text)
    is_fluff = _matches_any(FLUFF_PATTERNS, text)

    if is_listicle:
        reasons.append("listicle-shaped headline (e.g. 'N stocks to watch')")
    if is_filler:
        reasons.append("generic market-outlook filler with no new information")
    if is_fluff:
        reasons.append("motivational/PR fluff with no financial materiality")

    # No shape signal fired at all and there's a real event + numbers +
    # company backing it — this is not noise, full stop.
    if not (is_listicle or is_filler or is_fluff):
        if not has_material_event and not has_numbers and not has_company:
            reasons.append("no identifiable company, numbers, or material event type")
            return True, 30, reasons
        return False, 0, []

    # A shape signal fired. If there is nothing grounding it (no material
    # event type AND no numbers), it's unambiguous noise -> heavy penalty.
    if not has_material_event and not has_numbers:
        reasons.append("noise-shaped headline with no material event or numbers backing it")
        return True, 45, reasons

    # Shape signal fired but there IS a material event or real numbers behind
    # it (e.g. "5 numbers from SEBI's record ₹500 crore fine on XYZ Bank") —
    # discount it for being clickbait-shaped, but don't nuke a real story.
    reasons.append("noise-shaped headline, but grounded in a material event/number — discounted, not rejected")
    return False, 15, reasons
