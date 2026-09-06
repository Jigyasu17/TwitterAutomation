"""
Content-type classification: SINGLE_EVENT / MARKET_EVENT / ROUNDUP /
CALENDAR / ADVICE / OPINION / FORECAST / MARKET_WRAP.

The India-relevance gate and noise filter both answer "is this on-topic /
not filler" — neither answers "is this actually ONE reportable event." A
"20 companies report results next week" calendar and a "Company X reports
₹5,000 crore profit" single event can both be on-topic, non-noise, and
India-relevant, yet only one of them is useful for ranking or drafting.
This module is that missing axis, feeding a targeted penalty into
classifier.calculate_scores and gating main-company resolution (a roundup
has no single subject company).

OPINION/ANALYSIS detection is deliberately context-aware, not a bare
keyword ban: a "why" question anchored to a real, quantified, completed
event ("Why did ABC shares fall 10% after results?") is hard news wearing
an explainer headline, not generic opinion — see _has_hard_news_anchor().
Only ungrounded "why"/"explained"/"outlook" framing gets down-weighted.
"""
import re
from typing import Any, Dict, Optional

SINGLE_EVENT = "SINGLE_EVENT"
MARKET_EVENT = "MARKET_EVENT"
ROUNDUP = "ROUNDUP"
CALENDAR = "CALENDAR"
ADVICE = "ADVICE"
OPINION = "OPINION"
FORECAST = "FORECAST"
MARKET_WRAP = "MARKET_WRAP"

# Content types that should lose out to SINGLE_EVENT/MARKET_EVENT in ranking
# unless the story clears the "exceptional development" escape hatch.
DOWN_WEIGHTED_TYPES = {ROUNDUP, CALENDAR, ADVICE, OPINION, FORECAST, MARKET_WRAP}

CALENDAR_PATTERNS = [
    r'\bto\s+(?:post|declare|announce|report)\s+earnings\b',
    r'\bto\s+post\s+results\b',
    r'\bearnings\s+(?:calendar|today|on\s+\w+\s+\d+)\b',
    r'\bcompanies?\s+(?:launch|launching)\s+ipos?\b',
    r'\b\d+\+?\s+companies\b',
    r'\bipos?\s+(?:launching|to\s+open)\s+next\s+week\b',
]

ROUNDUP_PATTERNS = [
    r'\bthis\s+week\b.*\b(raised|funding|ipo)\b',
    r'\braised\s+over\b',
    r'\bweekly\s+(roundup|wrap|digest)\b',
    r'\btop\s+\d+\s+(startups|companies|deals)\b',
]

ADVICE_PATTERNS = [
    r'\bshould\s+you\s+buy\b',
    r'\bstocks?\s+to\s+buy\b',
    r'\bwhat\s+investors?\s+should\s+do\b',
    r'\bshould\s+investors\b',
    r'\bbuy\s+or\s+sell\b',
    r'\bsubscribe\b.*\brecommendation',
]

# Forward-looking prediction/outlook framing — a QUESTION about what might
# happen, not an explanation of something that already did.
FORECAST_PATTERNS = [
    r'\bhow\s+will\b.*\bbehave\b',
    r'\bwhy\s+(?:will|may|might|could)\s+.*\brise\b',
    r'\bwhy\s+markets?\s+may\b',
    r'\bwill\s+\d{4}\s+be\b',
    r'\bwill\s+markets?\b',
    r'\bcan\s+the\s+market\b',
    r'\bwhat\s+to\s+expect\b',
    r'\bwhat\s+happens\s+next\b',
]

# Explicit, unambiguous opinion/analysis/explainer labels — a bare
# "Explained"/"Analysis" tag on a headline is a soft-content signal
# regardless of "why" wording, so these are checked on their own.
OPINION_LABEL_PATTERNS = [
    r'\|\s*explained\s*$',
    r'\bexplained\b',
    r'\banalysis\b',
    r'\boutlook\b',
    r'\b(view|perspective)\s*:',
    r'\bview\s+on\b',
    r'\bcould\s+this\b',
    r'\bhere.?s\s+why\b',
    r'\bexperts?\s+explain\b',
    r'\bfactors?\s+driving\b',
]

# A "why" question — down-weighted ONLY when it lacks a hard-news anchor
# (see _has_hard_news_anchor). Deliberately a bare word match rather than
# requiring an auxiliary verb immediately after "why": real headlines put a
# subject phrase in between ("why [India's IPO markets] are heating up"),
# so anchoring the exception on the anchor-check below is more reliable
# than trying to constrain the grammatical shape of the question itself.
WHY_QUESTION_PATTERN = re.compile(r'\bwhy\b', re.IGNORECASE)

# A quantified move tied to an explicit, completed cause — "10% after
# results", "shares fell 8% following the announcement". Present, this
# rescues an otherwise opinion-shaped "why" headline back to hard news.
HARD_NEWS_ANCHOR_PATTERN = re.compile(
    r'\d+(?:\.\d+)?\s*%.{0,25}\b(after|following|as|on)\b|\bafter\s+(earnings|results|profit|quarterly|q[1-4])\b',
    re.IGNORECASE,
)

# Routine ticker/live-blog wrap shapes — "Sensex Today", "Market Live",
# bare "N factors driving the market" — down-weighted UNLESS the move is
# big/named enough to be genuinely material (see _has_major_market_catalyst).
MARKET_WRAP_PATTERNS = [
    r'\bsensex\s+today\b',
    r'\bstock\s+market\s+live\b',
    r'\bmarket\s+live\b',
    r'\b\d+\s+factors?\s+(?:driving|behind|fueling)\s+(?:the\s+)?(?:market|rally|sensex|nifty)\b',
    r'\bwhat\s+will\s+drive\s+d-street\b',
]

MAJOR_CATALYST_KEYWORDS = re.compile(
    r'\b(crash|crashes|plunge|plunges|record\s+high|record\s+low|policy\s+announcement|'
    r'rate\s+(?:hike|cut)|historic|circuit)\b',
    re.IGNORECASE,
)
_POINTS_PATTERN = re.compile(r'\b([\d,]+)\s*(?:points?|pts)\b', re.IGNORECASE)

# A completed, quantified market move — distinguishes a real MARKET_EVENT
# ("Sensex rises 700 points as crude falls 5%") from a FORECAST about a
# possible future move ("why markets may rise tomorrow").
MARKET_MOVE_PATTERN = re.compile(
    r'\b(sensex|nifty|market|markets|stocks?|shares?)\b.{0,40}\b(rises?|rose|jumps?|surges?|falls?|fell|drops?|plunges?|gains?|climbs?)\b.{0,20}\d+(?:\.\d+)?\s*(?:%|points?|pts)\b',
    re.IGNORECASE,
)


def _matches_any(patterns, text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _has_hard_news_anchor(text: str) -> bool:
    return bool(HARD_NEWS_ANCHOR_PATTERN.search(text))


def _has_major_market_catalyst(text: str) -> bool:
    if MAJOR_CATALYST_KEYWORDS.search(text):
        return True
    pts_match = _POINTS_PATTERN.search(text)
    if pts_match:
        try:
            return float(pts_match.group(1).replace(",", "")) >= 1000
        except ValueError:
            return False
    return False


def classify_content_type(
    title: str,
    summary: str = "",
    company_count: int = 0,
    has_large_financial_figure: bool = False,
) -> str:
    """
    Returns one of SINGLE_EVENT / MARKET_EVENT / ROUNDUP / CALENDAR /
    ADVICE / OPINION / FORECAST / MARKET_WRAP.

    has_large_financial_figure is the "unless the roundup itself contains
    unusually important information" escape hatch — an exceptionally large
    number still earns SINGLE_EVENT-level treatment even inside an otherwise
    roundup-shaped headline.
    """
    text = f"{title or ''} {summary or ''}"

    if _matches_any(CALENDAR_PATTERNS, text) or company_count >= 5:
        return SINGLE_EVENT if has_large_financial_figure else CALENDAR

    if _matches_any(ROUNDUP_PATTERNS, text):
        return SINGLE_EVENT if has_large_financial_figure else ROUNDUP

    if _matches_any(ADVICE_PATTERNS, text):
        return ADVICE

    # Opinion/analysis/explainer — checked before FORECAST since both can
    # overlap on "why" phrasing, and OPINION's hard-news-anchor rescue must
    # get first look at ungrounded-vs-grounded "why" framing.
    has_why_question = bool(WHY_QUESTION_PATTERN.search(text))
    has_opinion_label = _matches_any(OPINION_LABEL_PATTERNS, text)
    if has_why_question or has_opinion_label:
        if not _has_hard_news_anchor(text):
            return OPINION
        # Hard-news-anchored "why" (e.g. "why did ABC shares fall 10% after
        # results?") falls through to the MARKET_MOVE/SINGLE_EVENT checks
        # below instead — it's event analysis, not generic opinion.

    if _matches_any(FORECAST_PATTERNS, text):
        return FORECAST

    if _matches_any(MARKET_WRAP_PATTERNS, text) and not _has_major_market_catalyst(text):
        return MARKET_WRAP

    if MARKET_MOVE_PATTERN.search(text):
        return MARKET_EVENT

    return SINGLE_EVENT


def content_type_penalty(content_type: str, has_large_financial_figure: bool = False) -> int:
    """
    Importance-score points subtracted for a down-weighted content type.
    SINGLE_EVENT and MARKET_EVENT get none. An exceptional financial figure
    softens the penalty even for a down-weighted type rather than zeroing it
    outright (still down-weighted relative to a clean single event, just less so).
    """
    if content_type not in DOWN_WEIGHTED_TYPES:
        return 0
    if has_large_financial_figure:
        return 10
    return 22
