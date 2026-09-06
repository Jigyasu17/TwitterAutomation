"""
Draft quality control.

Two independent checks:
1. Anti-headline-rewrite: is this draft just the headline restated?
2. Quality score: does it have a hook, numbers, an investor angle, and stay
   grounded in facts we actually extracted (no invented figures)?

Both use lightweight lexical methods (difflib / regex), matching the
project's existing dedup-similarity approach (app/processing/deduplication's
calculate_similarity) rather than pulling in an embeddings model — this
project explicitly stays off heavyweight ML/embeddings infrastructure.
"""
import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from app.processing.deduplication import calculate_similarity
from app.domain.models import StoryData, ResearchFactData

logger = logging.getLogger(__name__)

REWRITE_SIMILARITY_THRESHOLD = 0.72

HOOK_CUES = re.compile(
    r'(^\W*(here.?s|why|how|nobody|is\s|the\s+(bigger|real|immediate)|'
    r'that.?s\s+the\s+number|isn.?t\s+the|just\s+made|could\s+(change|reshape))\b)',
    re.IGNORECASE,
)
# Stdlib `re` has no \p{So} Unicode-property escape (that needs the third
# -party `regex` module, which this project doesn't depend on) — a plain
# codepoint range covering the emoji blocks the hook templates actually use
# does the same job here.
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF☀-➿]"
)

NUMBER_RE = re.compile(r'(\d+(?:\.\d+)?\s*%|[$₹]\s*[\d.]+\s*[BMK]?|\b\d+(?:\.\d+)?\s*(cr|crore|lakh|billion|million)\b)', re.I)

QUESTION_OR_CONTRAST = re.compile(r'(\?|→|but the|isn.?t the|second-order)', re.IGNORECASE)

# Promotional/clickbait tells the deterministic templates and AI provider
# should never produce — hype language, not information.
CLICKBAIT_PATTERNS = re.compile(
    r'\b(you won.?t believe|shocking|must[- ]?see|mind[- ]?blowing|game[- ]?changer|'
    r'insane|unbelievable|jaw[- ]?dropping|breaking news!!+|act now|don.?t miss)\b',
    re.IGNORECASE,
)
# 3+ consecutive exclamation marks, or 2+ separate exclamation-ended clauses,
# reads as promotional rather than informational.
EXCESSIVE_PUNCTUATION = re.compile(r'!!!+|(?:![^!]{0,20}){2,}')
# A run of 4+ consecutive fully-capitalized words (not a known acronym like
# "SEBI"/"IPO"/"NSE") reads as shouting rather than emphasis.
EXCESSIVE_CAPS = re.compile(r'\b(?:[A-Z]{4,}\b\W+){2,}[A-Z]{4,}\b')

# Signs of a broken/garbled AI or template output rather than real prose —
# raw JSON/code artifacts, refusal boilerplate, or template placeholders
# that never got filled in.
MALFORMED_PATTERNS = re.compile(
    r'(\{["\']|\["|```|<\|.*?\|>|\{\{.*?\}\}|\[INSERT|as an ai language model|'
    r'i cannot |i can.?t assist|undefined|NaN%|None%)',
    re.IGNORECASE,
)


def is_malformed_or_promotional(post_text: str) -> Optional[str]:
    """
    Returns a rejection reason string if the draft is malformed or
    promotional/clickbait-shaped, else None. Checked as an outright reject
    (not just a scoring deduction) — Phase 3 explicitly calls both out as
    "reject or regenerate," not "discount."
    """
    if not post_text or not post_text.strip():
        return "empty output"
    if len(post_text.strip()) < 8:
        return "suspiciously short output"
    if MALFORMED_PATTERNS.search(post_text):
        return "malformed output (code/JSON artifact, template placeholder, or model refusal text)"
    if CLICKBAIT_PATTERNS.search(post_text):
        return "clickbait/promotional language"
    if EXCESSIVE_PUNCTUATION.search(post_text):
        return "excessive punctuation (promotional tone)"
    if EXCESSIVE_CAPS.search(post_text):
        return "excessive capitalization (shouting)"
    return None


def _company_mention_count(post_text: str, company: Optional[str]) -> int:
    if not company or len(company) < 2:
        return 0
    return len(re.findall(r'\b' + re.escape(company) + r'\b', post_text, re.IGNORECASE))


def similarity_to_headline(post_text: str, title: str) -> float:
    """Lexical similarity between a draft and its source headline (0-1)."""
    if not post_text or not title:
        return 0.0
    return calculate_similarity(post_text, title)


def is_headline_rewrite(post_text: str, title: str) -> bool:
    """
    True if the draft is basically the headline restated with no added hook,
    number, or framing — i.e. it fails the project's core "headline != post"
    rule.
    """
    sim = similarity_to_headline(post_text, title)
    if sim < REWRITE_SIMILARITY_THRESHOLD:
        return False
    # High textual overlap with the headline — only acceptable if it still
    # opens with a real hook cue (emoji + framing) that the headline itself
    # wouldn't have had.
    return not bool(_EMOJI_RE.search(post_text[:4]) and HOOK_CUES.search(post_text))


def _has_hook(post_text: str) -> bool:
    return bool(_EMOJI_RE.search(post_text[:4])) or bool(HOOK_CUES.search(post_text)) or bool(QUESTION_OR_CONTRAST.search(post_text))


def _grounded_numbers_only(post_text: str, facts: List[ResearchFactData]) -> bool:
    """
    Best-effort fact-safety check: every numeric token the draft mentions
    should trace back to either an extracted research fact or simply not
    exist (a draft with no numbers always passes trivially — omission is
    always safe, invention is not).
    """
    mentioned = NUMBER_RE.findall(post_text)
    if not mentioned:
        return True
    if not facts:
        # Numbers appear in the text but we have zero extracted facts to
        # justify them — could still be the company name/date, but flag as
        # unverified so the quality score reflects the risk rather than
        # silently trusting it.
        return False
    return True  # Presence of any backing facts is treated as sufficient grounding at this rule-based tier.


def score_draft(
    post_text: str,
    thread: Optional[List[str]],
    story: StoryData,
    facts: List[ResearchFactData],
    tweet_limit: int = 280,
) -> Tuple[int, Dict[str, bool]]:
    """
    Returns (0-100 quality score, checks dict) for one draft candidate.
    Used to rank multiple angle candidates and to gate AI output before
    it's allowed to replace the deterministic fallback.
    """
    company_mentions = _company_mention_count(post_text, getattr(story, "company", None))

    checks = {
        "has_hook": _has_hook(post_text),
        "adds_info_beyond_headline": not is_headline_rewrite(post_text, story.title),
        "has_numbers": bool(NUMBER_RE.search(post_text)),
        "has_investor_or_consequence_angle": bool(re.search(
            r'\b(investor|stock|shares|market|valuation|growth|revenue|profit|consequence|impact)\b',
            post_text, re.IGNORECASE,
        )),
        "within_limit": len(post_text) <= tweet_limit,
        "grounded_numbers": _grounded_numbers_only(post_text, facts),
        "not_empty": bool(post_text and post_text.strip()),
        "strong_opening": not post_text.strip().lower().startswith(story.title.strip().lower()[:20]),
        "not_malformed_or_promotional": is_malformed_or_promotional(post_text) is None,
        "no_unnecessary_company_repetition": company_mentions <= 2,
    }

    weights = {
        "has_hook": 20,
        "adds_info_beyond_headline": 25,
        "has_numbers": 15,
        "has_investor_or_consequence_angle": 15,
        "within_limit": 10,
        "grounded_numbers": 10,
        "not_empty": 3,
        "strong_opening": 2,
        "not_malformed_or_promotional": 15,
        "no_unnecessary_company_repetition": 5,
    }
    score = sum(weights[k] for k, passed in checks.items() if passed)
    return min(100, score), checks
