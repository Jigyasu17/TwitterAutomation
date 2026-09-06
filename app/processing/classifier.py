import re
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional

from app.processing.source_quality import build_legacy_source_priorities, get_source_quality_score, get_source_tier
from app.processing.relevance import calculate_india_relevance, relevance_multiplier
from app.processing.noise_filter import detect_noise
from app.processing.entity_roles import (
    REGULATORS, NON_COMPANY_ENTITIES, filter_non_company_entities, is_non_company,
)
from app.processing.content_type import classify_content_type, content_type_penalty, ROUNDUP, CALENDAR
from app.processing.staleness import staleness_multiplier

logger = logging.getLogger(__name__)

# Predefined dictionary for entity extraction.
# SEBI/RBI (regulators) and Reuters/Bloomberg (wire services) are
# deliberately NOT here — see app.processing.entity_roles for why: a
# regulator or wire service can be mentioned in a story without ever being
# the story's subject COMPANY, and Google News RSS summaries literally echo
# "<title> — <publisher>", so leaving a publisher name in this dict caused it
# to be picked up as "the company" for headlines with no other company match.
KNOWN_COMPANIES = {
    "tata motors", "tata", "reliance", "jio", "infosys", "wipro", "hdfc", "sbi",
    "navi", "zepto", "zomato", "paytm", "adani", "ather energy", "ather", "ola",
    "lic", "bse", "nse", "makemytrip", "cult.fit", "cultfit",
    "biocon", "lohia corp", "sembcorp", "carlsberg", "manipal health", "l&t",
    "infy", "air india", "indigo", "tcs", "byjus", "physics wallah", "swiggy",
    "google", "apple", "microsoft", "amazon", "tesla", "nvidia"
}


def _keyword_hit(keywords, text: str) -> bool:
    """
    Substring match for keywords of 4+ characters; word-boundary match for
    short (<=3 char) keywords. A bare `"ai" in text` or `"cr" in text` check
    silently matches inside ordinary words — "gain" contains "ai", "increase"
    contains "cr" — which is exactly how "IndiGo jumps 4.5%, HPCL surges
    6.6%..." was miscategorized as TECH (matched on "ai" inside "gain").
    Longer keywords ("semiconductor", "artificial intelligence") are specific
    enough that plain substring matching was never the problem.
    """
    for k in keywords:
        if len(k) <= 3:
            if re.search(r'\b' + re.escape(k) + r'\b', text):
                return True
        elif k in text:
            return True
    return False


# Movement verbs used to detect a completed (not merely predicted) stock/
# market move — all 4+ chars, safe for plain substring matching.
_STOCK_MOVE_VERBS = [
    "jump", "jumps", "surge", "surges", "gain", "gains", "rally", "rallies",
    "climb", "climbs", "soar", "soars", "fall", "falls", "drop", "drops",
    "slide", "slides", "plunge", "plunges", "slip", "slips", "rise", "rises", "rose",
]
_PCT_PATTERN = re.compile(r'\d+(?:\.\d+)?\s*%')

KNOWN_PEOPLE = {
    "mukesh ambani", "ambani", "ratan tata", "nikhil kamath", "bhavish aggarwal", 
    "byju raveendran", "natarajan chandrasekaran", "karan adani", "gautam adani",
    "kunal shah", "sridhar vembu", "deepinder goyal", "ritesh agarwal"
}

KNOWN_COUNTRIES = {
    "india", "us", "usa", "china", "uk", "germany", "japan", "singapore", 
    "uae", "vietnam", "france", "spain", "russia", "bangladesh"
}

KNOWN_SECTORS = {
    "ev": ["ev", "electric vehicle", "battery", "lithium"],
    "fintech": ["fintech", "payment", "banking", "lending", "wallet", "upi"],
    "telecom": ["telecom", "5g", "spectrum", "broadband", "jio", "airtel"],
    "ai": ["ai", "artificial intelligence", "llm", "deep learning", "machine learning"],
    "saas": ["saas", "software as a service", "enterprise software"],
    "e-commerce": ["e-commerce", "quick commerce", "delivery", "retail", "marketplace"],
    "semiconductor": ["semiconductor", "chip", "foundry", "silicon", "fab"],
    "automobile": ["automobile", "automotive", "car", "suv", "truck", "motors"],
    "banking": ["banking", "bank", "lender", "credit"],
    "pharma": ["pharma", "biotech", "healthcare", "hospital", "drug"]
}

# Source Priority Configurations (configurable trust mappings).
# Derived from app.processing.source_quality's tier table so there is one
# canonical source-trust ranking; kept as a flat dict here since
# source_discovery.py and drafts/builder.py already import this exact name.
SOURCE_PRIORITIES = build_legacy_source_priorities()

def clean_and_lower(text: str) -> str:
    return text.lower().strip() if text else ""

def classify_category(title: str, summary: str) -> Tuple[str, List[str]]:
    """
    Classifies a story into a primary category and extracts secondary tags.
    Primary Categories: MARKET, STOCK, BUSINESS, STARTUP, FUNDING, IPO, M&A, ECONOMY, REGULATORY, TECH, GLOBAL, OTHER
    """
    text = clean_and_lower(f"{title} {summary}")
    secondary_tags = []

    # 1. IPO
    if _keyword_hit(["ipo", "drhp", "draft papers", "listing day", "listings", "public issue"], text):
        primary = "IPO"
        if "sebi" in text: secondary_tags.append("REGULATORY")
        if "gmp" in text or "premium" in text: secondary_tags.append("MARKET")
        return primary, list(set(secondary_tags))

    # 2. FUNDING
    if _keyword_hit(["raises", "funding round", "series a", "series b", "series c", "seed funding", "venture capital", "raised $", "raised ₹"], text):
        primary = "FUNDING"
        secondary_tags.append("STARTUP")
        if "fintech" in text: secondary_tags.append("FINTECH")
        return primary, list(set(secondary_tags))

    # 3. M&A
    if _keyword_hit(["acquisition", "acquires", "merger", "buyout", "takeover", "merges with"], text):
        primary = "M&A"
        if "deal" in text: secondary_tags.append("BUSINESS")
        return primary, list(set(secondary_tags))

    # 4. REGULATORY
    if _keyword_hit(["rbi", "sebi", "mca", "regulatory", "penalty", "sebi bars", "rbi imposes", "compliance", "notice"], text):
        primary = "REGULATORY"
        if "bank" in text or "fintech" in text: secondary_tags.append("FINANCE")
        return primary, list(set(secondary_tags))

    # 5. MARKET
    if _keyword_hit(["sensex", "nifty", "bull run", "stock market", "indices", "nasdaq", "bse", "nse", "global markets"], text):
        primary = "MARKET"
        if "shares" in text: secondary_tags.append("STOCK")
        return primary, list(set(secondary_tags))

    # 5b. MARKET (multiple distinct % moves in one headline — a multi-stock/
    # multi-sector market movement roundup like "IndiGo jumps 4.5%, HPCL
    # surges 6.6%, tyre stocks gain up to 7%..." — that's a market-wide
    # movement story, not a single stock, and previously fell through to
    # TECH purely because "gain" contains the substring "ai").
    pct_matches = _PCT_PATTERN.findall(text)
    has_move_verb = _keyword_hit(_STOCK_MOVE_VERBS, text)
    if len(pct_matches) >= 2 and has_move_verb:
        return "MARKET", ["STOCK"]

    # 6. STOCK (single-name movement — either the older fixed phrases, or a
    # single % figure paired with a movement verb)
    if _keyword_hit(["dividend", "bonus issue", "stock split", "shares jump", "shares fall", "shares rally", "ticker"], text) \
            or (len(pct_matches) == 1 and has_move_verb):
        primary = "STOCK"
        secondary_tags.append("MARKET")
        return primary, list(set(secondary_tags))

    # 7. ECONOMY
    if _keyword_hit(["gdp", "inflation", "cpi", "fiscal deficit", "tax collection", "gst", "economic growth", "interest rates"], text):
        primary = "ECONOMY"
        if "rbi" in text: secondary_tags.append("REGULATORY")
        return primary, list(set(secondary_tags))

    # 8. STARTUP
    if _keyword_hit(["startup", "unicorn", "founder", "incubator", "y combinator"], text):
        primary = "STARTUP"
        if "funding" in text or "round" in text: secondary_tags.append("FUNDING")
        return primary, list(set(secondary_tags))

    # 9. TECH
    if _keyword_hit(["semiconductor", "ai", "artificial intelligence", "software", "chip", "robotics", "ev", "electric vehicle"], text):
        primary = "TECH"
        if re.search(r'\bev\b', text): secondary_tags.append("EV")
        if re.search(r'\bai\b', text): secondary_tags.append("AI")
        return primary, list(set(secondary_tags))

    # 10. GLOBAL
    if _keyword_hit(["fed hike", "us inflation", "china economy", "opec", "global oil", "eurozone"], text):
        primary = "GLOBAL"
        secondary_tags.append("ECONOMY")
        return primary, list(set(secondary_tags))

    # 11. BUSINESS (Capex / Expansion / Corporate announcements)
    if _keyword_hit(["capex", "investment", "factory", "manufacturing", "announces", "plans to invest", "expansion", "jv"], text):
        primary = "BUSINESS"
        if re.search(r'\bev\b', text): secondary_tags.append("TECH")
        return primary, list(set(secondary_tags))

    return "OTHER", []

def identify_event_type(title: str) -> str:
    """Classifies the primary event action type from the title."""
    t = title.lower()
    if "raises" in t or "raised" in t or "funding" in t:
        return "FUNDING"
    if "acquires" in t or "acquisition" in t or "buyout" in t:
        return "ACQUISITION"
    if "merger" in t or "merges" in t:
        return "MERGER"
    if "files drhp" in t or "draft papers" in t or "files ipo" in t:
        return "IPO_FILING"
    if "ipo pricing" in t or "price band" in t or "ipo price" in t:
        return "IPO_PRICING"
    # IPO_LISTING requires evidence of an ACTUAL listing/debut/trading event
    # — the bare word "listing" is not enough. "NSE IPO listing date,
    # timeline: when the issue is expected to hit exchanges" and "India's
    # biggest potential listing" are still in the announcement/planning
    # phase, not a completed listing; only phrases describing the listing
    # itself (shares actually listed/debuting/trading) count.
    _listing_negative = any(p in t for p in [
        "listing date", "listing timeline", "listing plans", "potential listing",
        "biggest listing", "ipo timing", "expected to hit", "could become",
    ])
    _listing_positive = any(p in t for p in [
        "shares listed", "lists at", "lists on nse", "lists on bse", "makes market debut",
        "market debut", "shares debut", "stock debuts", "debuts on", "trading begins",
        "begins trading", "debut on dalal street", "lists with a premium", "debuts at",
    ])
    if _listing_positive and not _listing_negative:
        return "IPO_LISTING"
    if "ipo" in t:
        return "IPO_ANNOUNCEMENT"
    if "q1" in t or "q2" in t or "q3" in t or "q4" in t or "quarterly" in t or "earnings" in t:
        if "profit" in t or "surges" in t or "surged" in t:
            return "PROFIT_UPDATE"
        if "revenue" in t:
            return "REVENUE_UPDATE"
        return "EARNINGS"
    if "invest" in t or "investment" in t or "capex" in t or "plans to spend" in t:
        return "INVESTMENT"
    if "shares jump" in t or "shares surge" in t or "stock climbs" in t or "shares fall" in t or "shares drop" in t or "hits record high" in t:
        return "STOCK_MOVEMENT"
    if "launches" in t or "unveils" in t or "introduces" in t:
        return "PRODUCT_LAUNCH"
    if "partners" in t or "partnership" in t or "signs agreement" in t:
        return "PARTNERSHIP"
    if "penalty" in t or "regulatory action" in t or "fines" in t or "sebi bars" in t or "rbi imposes" in t:
        return "REGULATORY_ACTION"
    if "appoints" in t or "ceo" in t or "cfo" in t or "resigns" in t or "chairman" in t:
        return "LEADERSHIP_CHANGE"
    if "expands" in t or "expansion" in t:
        return "EXPANSION"
    if "layoff" in t or "lays off" in t or "job cuts" in t:
        return "LAYOFF"
    if "lawsuit" in t or "sues" in t or "legal" in t:
        return "LEGAL"
    if "rate hike" in t or "gst rate" in t or "policy change" in t:
        return "POLICY_CHANGE"
        
    return "OTHER"

def extract_entities(title: str, summary: str) -> Dict[str, List[str]]:
    """
    Extracts structured entities (Companies, People, Sectors, Countries)
    using rule-based matching and capitalization heuristics.
    """
    full_text = f"{title} {summary}"
    text_lower = full_text.lower()

    extracted = {
        "Companies": [],
        "People": [],
        "Sectors": [],
        "Countries": [],
        "Regulators": [],
    }

    # 0. Regulators are their own bucket, never "Companies" — SEBI/RBI can be
    # a legitimate entity a story is about without ever being the subject
    # COMPANY (see app.processing.entity_roles).
    for regulator in REGULATORS:
        if re.search(r'\b' + re.escape(regulator) + r'\b', text_lower):
            extracted["Regulators"].append(regulator.upper() if len(regulator) <= 5 else regulator.title())

    # 1. Match known companies dictionary
    for company in KNOWN_COMPANIES:
        # Match as a whole word boundary
        if re.search(r'\b' + re.escape(company) + r'\b', text_lower):
            # Title case it for styling
            name = company.upper() if company in ["bse", "nse", "lic", "tcs", "l&t", "infy"] else company.title()
            extracted["Companies"].append(name)

    # Heuristic dynamic company extraction: Look for capitalized word phrases preceding action verbs
    # E.g. "[Zepto] plans to file..." or "[Tata Motors] announces..." or
    # "[Quest Global] Said to Pick Banks..." (the "said to <verb>" form is
    # common in Bloomberg/Reuters-style sourced reporting).
    # Note: [Ss]aid rather than a bare "said" — Bloomberg/Reuters-style
    # sourced headlines ("Quest Global Said to Pick Banks...") capitalize
    # "Said" as a reporting verb, unlike the other lowercase verbs below
    # which follow normal headline casing; the whole match runs against the
    # raw (not lowercased) title, so this needed its own case handling.
    action_verbs = r'(?:raises|invests|reports|announces|launches|files|plans|debuts|lists|unveils|partners|acquires|merges|hires|eyes|seeks|[Ss]aid\s+to\s+\w+)'
    company_regex = r'\b([A-Z][a-zA-Z0-9&]*(?:\s+[A-Z][a-zA-Z0-9&]*)*)\s+' + action_verbs
    matches = re.findall(company_regex, title)
    for match in matches:
        match_clean = match.strip()
        # Filter out common false positives (days of week, stopwords, and
        # any known regulator/wire-service/publisher name — see
        # entity_roles.NON_COMPANY_ENTITIES; this is what previously let
        # "Reuters"/"Bloomberg" through when they appeared in the RSS
        # summary's "<title> — <publisher>" suffix next to a matching verb).
        if match_clean.upper() not in {"SEBI", "RBI", "INDIA", "US", "IPO", "GMP", "SENSEX", "NIFTY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"} \
                and match_clean.lower() not in NON_COMPANY_ENTITIES:
            if match_clean not in extracted["Companies"]:
                # Check if it contains a known lowercase match first to avoid duplicate representations
                if match_clean.lower() not in [c.lower() for c in extracted["Companies"]]:
                    extracted["Companies"].append(match_clean)

    # Final defensive filter: drop any regulator/wire-service/publisher name
    # that slipped into Companies via either extraction path above. One
    # canonical exclusion list (entity_roles.NON_COMPANY_ENTITIES), checked
    # here as the last line of defense rather than duplicated per-caller.
    extracted["Companies"] = filter_non_company_entities(extracted["Companies"])

    # 2. Match known people
    for person in KNOWN_PEOPLE:
        if re.search(r'\b' + re.escape(person) + r'\b', text_lower):
            extracted["People"].append(person.title())
            
    # Heuristic dynamic people names: Look for Capitalized Sequences following Titles
    people_regex = r'\b(?:CEO|Founder|Chairman|MD|CFO)\s+([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+)\b'
    pm_matches = re.findall(people_regex, full_text)
    for pm in pm_matches:
        pm_clean = pm.strip()
        if pm_clean not in extracted["People"] and pm_clean.lower() not in [p.lower() for p in extracted["People"]]:
            extracted["People"].append(pm_clean)

    # 3. Match sectors
    for sector, keywords in KNOWN_SECTORS.items():
        if any(re.search(r'\b' + re.escape(k) + r'\b', text_lower) for k in keywords):
            extracted["Sectors"].append(sector.upper())
            
    # 4. Match countries
    for country in KNOWN_COUNTRIES:
        if re.search(r'\b' + re.escape(country) + r'\b', text_lower):
            # Normalize UK/US representations
            name = "United States" if country in ["us", "usa"] else country.title()
            extracted["Countries"].append(name)
            
    # Remove duplicates and clean
    for k in extracted:
        extracted[k] = list(set(extracted[k]))

    return extracted


def resolve_main_company(
    entities: Dict[str, Any],
    content_type: Optional[str] = None,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """
    Picks the single subject company for a story, or None when there isn't
    a reliable one.

    Never returns a regulator/wire-service/publisher (extract_entities()
    already keeps those out of "Companies" entirely — see entity_roles).
    Also refuses to pick an arbitrary company out of a ROUNDUP/CALENDAR
    story or one that simply names too many companies to have one subject:
    "Q1 Results: Reliance, JSW Steel, Federal Bank, Havells, Tata Technologies,
    Oberoi Realty, others to post earnings..." should not silently become a
    story "about" whichever of those six happened to be extracted first.
    """
    companies = (entities or {}).get("Companies", [])
    # A fallback carried over from an earlier pass (e.g. story.company on a
    # story processed before this fix existed) could itself be a stale
    # wire-service/regulator name — never surface that either.
    safe_fallback = None if is_non_company(fallback) else fallback
    if content_type in {ROUNDUP, CALENDAR}:
        return None
    if not companies:
        return safe_fallback
    if len(companies) > 3:
        return None
    return companies[0]


def extract_financial_amount(title: str) -> float:
    """
    Extracts the dollar/rupee equivalent value from a title string to score financial significance.
    Returns value in USD millions.
    - $100M -> 100
    - $1B -> 1000
    - Rs 500 Cr (approx $60M) -> 60
    - Rs 5,000 crore (approx $600M) -> 600
    """
    title_clean = title.replace(",", "").lower()
    
    # 1. Match USD Millions/Billions
    usd_b_match = re.search(r'\$\s*(\d+(?:\.\d+)?)\s*(?:billion|b)\b', title_clean)
    if usd_b_match:
        return float(usd_b_match.group(1)) * 1000.0
        
    usd_m_match = re.search(r'\$\s*(\d+(?:\.\d+)?)\s*(?:million|m)\b', title_clean)
    if usd_m_match:
        return float(usd_m_match.group(1))

    # 2. Match Rupee Crores (1 Crore approx = $120k, so 100 Crores approx = $12M)
    cr_match = re.search(r'(?:rs|inr|rupee|rupees|₹)\s*(\d+(?:\.\d+)?)\s*(?:crore|cr|crores)\b', title_clean)
    if cr_match:
        rupee_crore = float(cr_match.group(1))
        # Convert Rupee Crores to USD Millions (divide by 8.3 approx)
        return rupee_crore / 8.3
        
    # 3. Alternate Crore formatting (e.g. 500cr)
    alt_cr_match = re.search(r'\b(\d+(?:\.\d+)?)\s*(?:cr|crores)\b', title_clean)
    if alt_cr_match:
        return float(alt_cr_match.group(1)) / 8.3
        
    return 0.0

def _freshness_bonus(published_at: Optional[datetime]) -> int:
    """
    Small, bounded freshness signal (max 10 pts) added to importance so a
    just-broke event outranks a stale one of similar weight — without
    letting freshness alone dominate over materiality (a 2-hour-old major
    regulatory action must still beat a 5-minute-old irrelevant filler
    story, which it does here since noise/materiality swing 30-45+ points
    while freshness swings at most 10).
    """
    if not published_at:
        return 0
    try:
        now = datetime.utcnow()
        ref = published_at.replace(tzinfo=None) if getattr(published_at, "tzinfo", None) else published_at
        hours_ago = (now - ref).total_seconds() / 3600.0
    except Exception:
        return 0
    if hours_ago < 0:
        hours_ago = 0
    if hours_ago <= 1:
        return 10
    if hours_ago <= 3:
        return 8
    if hours_ago <= 6:
        return 6
    if hours_ago <= 12:
        return 4
    if hours_ago <= 24:
        return 2
    return 0


def _key_reason(
    market_impact: int, fin_sig: int, novelty: int, india_relevance: int,
    noise_penalty: int, noise_reasons: List[str], event_type: Optional[str],
    company: Optional[str] = None,
) -> str:
    """Deterministic one-line explanation of the single biggest driver behind a story's rank."""
    who = company or "This story"
    if noise_penalty >= 30:
        return f"Down-ranked: {noise_reasons[0] if noise_reasons else 'noise-shaped headline with no material backing'}."
    # Normalize each candidate driver to a comparable 0-1 scale, pick the winner.
    candidates = [
        (market_impact / 25.0, f"{who} is involved in a market-moving event (regulatory action, record move, or major shift)."),
        (fin_sig / 20.0, f"{who}'s story carries a significant financial figure."),
        (novelty / 15.0, f"This is a first-of-its-kind or record-setting development for {who}."),
        (india_relevance / 100.0, f"Directly tied to Indian markets/regulators, which is this feed's core focus."),
    ]
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[0][1]


def calculate_scores(
    title: str,
    summary: str,
    source_name: str,
    source_count: int = 1,
    entities: Optional[Dict[str, Any]] = None,
    event_type: Optional[str] = None,
    country: Optional[str] = None,
    published_at: Optional[datetime] = None,
) -> Tuple[int, int, int, int, Dict[str, Any]]:
    """
    Computes rule-based scores (0-100) for Importance, Postability, and Confidence.

    entities/event_type/country/published_at are optional so existing callers
    that only pass (title, summary, source_name, source_count) keep working —
    when omitted, the India-relevance gate, noise filter, and freshness bonus
    simply contribute their neutral defaults instead of being skipped
    entirely broken.

    Returns:
        Tuple: (importance_score, postability_score, confidence_score, final_score, score_breakdown)
    """
    entities = entities or {}
    t = title.lower()
    s = (summary or "").lower()
    text = f"{t} {s}"
    
    # --- A. Importance Subscores (Max 100) ---
    # 1. Market Impact (Max 25)
    market_impact = 5
    if any(k in text for k in ["rbi penalty", "sebi penalty", "sebi bars", "rbi imposes", "regulatory probe"]):
        market_impact = 22
    elif any(k in text for k in ["sensex record", "nifty record", "all-time high", "market crash", "stocks crash"]):
        market_impact = 20
    elif any(k in text for k in ["earnings surge", "quarterly profit jumps", "shares surge", "shares plunge"]):
        market_impact = 15
    elif any(k in text for k in ["ipo file", "draft papers", "drhp", "ipo listing", "debuts on market"]):
        market_impact = 15
    elif any(k in text for k in ["investment", "capex", "expands", "expansion"]):
        market_impact = 10
        
    # 2. Financial Significance (Max 20)
    fin_amount = extract_financial_amount(title)
    if fin_amount >= 1000.0:    # > $1B or ~₹8,300 Cr
        fin_sig = 20
    elif fin_amount >= 100.0:   # > $100M or ~₹830 Cr
        fin_sig = 17
    elif fin_amount >= 10.0:    # > $10M or ~₹83 Cr
        fin_sig = 12
    elif fin_amount > 0.0:      # Any amount
        fin_sig = 8
    else:
        fin_sig = 2
        # Fallback keyword checks if no numerical amounts match
        if "billion" in text: fin_sig = 15
        elif _keyword_hit(["million", "crore", "cr"], text): fin_sig = 10
        
    # 3. Novelty (Max 15)
    novelty = 5
    if any(k in text for k in ["breaking", "first time", "record high", "historic", "landmark", "unprecedented", "sets record"]):
        novelty = 15
    elif any(k in text for k in ["surges", "plunges", "slashed", "hikes", "bans"]):
        novelty = 10
        
    # 4. Audience Interest (Max 15)
    aud_interest = 5
    # High interest topics for market followers: IPOs, Hot Startups, Funding, EV, Ambani, Tata, RBI rules
    if any(k in text for k in ["ipo", "gmp", "zepto", "tata", "ambani", "reliance", "navi", "funding round"]):
        aud_interest = 14
    elif _keyword_hit(["ev", "electric vehicle", "ai", "semiconductor", "stock market", "inflation"], text):
        aud_interest = 11
        
    # 5. Discussion Potential (Max 15)
    disc_potential = 5
    # Things that spark opinions/debate: policy rates, layoffs, startup valuations, bans, losses
    if any(k in text for k in ["layoff", "job cuts", "ban", "loss", "valuation drops", "valuation cut", "rate hike", "tax", "gst"]):
        disc_potential = 13
    elif any(k in text for k in ["ipo pricing", "valuing at", "investment"]):
        disc_potential = 10
        
    # 6. Source Confidence (Max 10) — driven by the source-quality tier table
    # rather than a flat lookup, so an unrecognized/aggregator source (Tier 4)
    # scores meaningfully lower than a Tier 2 financial publication.
    source_base_score = get_source_quality_score(source_name)
    source_tier = get_source_tier(source_name)
    # Map 0-100 source score to 0-10 subscore
    source_confidence_sub = int(source_base_score / 10)

    # 7. India relevance gate — scales importance up/down based on how
    # directly this story connects to Indian markets/regulators/companies.
    india_relevance = calculate_india_relevance(title, summary, entities, country)
    india_mult = relevance_multiplier(india_relevance)

    # 8. Freshness — small bounded bonus for recency (see _freshness_bonus).
    freshness_bonus = _freshness_bonus(published_at)

    # 9. Noise filter — listicles, generic outlook filler, motivational PR.
    has_numeric_facts = fin_amount > 0.0
    is_noise, noise_penalty, noise_reasons = detect_noise(
        title, summary, entities, event_type, has_numeric_facts
    )

    # 10. Content type — is this one reportable event, or a roundup/
    # calendar/advice/opinion/forecast piece competing unfairly against one?
    company_count = len((entities or {}).get("Companies", []))
    has_large_financial_figure = fin_amount >= 1000.0
    content_type = classify_content_type(
        title, summary, company_count=company_count,
        has_large_financial_figure=has_large_financial_figure,
    )
    content_penalty = content_type_penalty(content_type, has_large_financial_figure)

    # 11. Staleness decay — an ancient story shouldn't compete with today's
    # news just because its underlying fundamentals once scored well.
    staleness_mult = staleness_multiplier(published_at, event_type, title, summary)

    # Total Importance (sum of all subscores + freshness), then apply the
    # India-relevance and staleness multipliers, then subtract noise/content
    # penalties last so a down-weighted story can't be rescued back above
    # threshold by a lucky relevance/freshness combination.
    raw_importance = market_impact + fin_sig + novelty + aud_interest + disc_potential + source_confidence_sub + freshness_bonus
    importance_score = int(round(raw_importance * india_mult * staleness_mult)) - noise_penalty - content_penalty
    # Clamp between 0 and 100
    importance_score = min(max(importance_score, 0), 100)

    # --- B. Postability Score (Max 100) ---
    # Suite of indicators that make an X post clickable
    post_score = 30

    # Indicator 1: Big brand name (Ambani, Tata, Tesla, Wipro, Zepto, etc.) -> +25
    has_brand = any(b in text for b in ["tata", "reliance", "ambani", "zepto", "navi", "zomato", "paytm", "adani", "physics wallah", "cult.fit", "ather", "make_my_trip"])
    if has_brand:
        post_score += 25

    # Indicator 2: Explicit financial numbers in title -> +20
    if fin_amount > 0.0 or any(k in t for k in ["$", "₹", "rs", "crore", "cr", "billion", "million"]):
        post_score += 20

    # Indicator 3: X-friendly keywords (surges, record, crash, layoff, secrets, why, how, boom) -> +15
    if any(k in text for k in ["surge", "plunge", "crash", "layoff", "record", "why", "how", "warning", "ban"]):
        post_score += 15

    # Indicator 4: Categorical priority (Startups, Funding, and IPOs have higher X engagement)
    if "ipo" in text or "funding" in text or "startup" in text:
        post_score += 10

    # Noise penalty applies at a lighter weight here — a listicle-shaped,
    # ungrounded headline is also a weak post, just not to the same degree
    # it tanks importance.
    post_score -= int(noise_penalty * 0.6)

    postability_score = min(max(post_score, 0), 100)

    # --- C. Confidence Score (Max 100) ---
    # Based on the trust score of the reporting source + confirmation count
    confidence_score = source_base_score
    # Duplicate group confirmation bonus: +15 for 2 sources, +25 for 3+ sources
    if source_count == 2:
        confidence_score += 15
    elif source_count >= 3:
        confidence_score += 25

    confidence_score = min(max(confidence_score, 0), 100)

    # --- D. Final Weighted Score ---
    # Formula: Importance * 0.50 + Postability * 0.35 + Confidence * 0.15
    # Can be adjusted via config
    final_score = int(
        (importance_score * 0.50) +
        (postability_score * 0.35) +
        (confidence_score * 0.15)
    )
    final_score = min(max(final_score, 0), 100)

    key_reason = _key_reason(
        market_impact, fin_sig, novelty, india_relevance, noise_penalty, noise_reasons, event_type
    )

    breakdown = {
        "market_impact": market_impact,
        "financial_significance": fin_sig,
        "novelty": novelty,
        "audience_interest": aud_interest,
        "discussion_potential": disc_potential,
        "source_confidence_sub": source_confidence_sub,
        # --- New signals (news-quality overhaul) ---
        "india_relevance": india_relevance,
        "india_relevance_multiplier": india_mult,
        "source_quality_tier": source_tier,
        "source_quality_score": source_base_score,
        "freshness_bonus": freshness_bonus,
        "noise_penalty": noise_penalty,
        "noise_reasons": noise_reasons,
        "content_type": content_type,
        "content_type_penalty": content_penalty,
        "staleness_multiplier": staleness_mult,
        "key_reason": key_reason,
        # "Why this story ranked" — x/10 ratings for the dashboard panel.
        "rating_market_relevance": round(min(market_impact / 25.0, 1.0) * 10, 1),
        "rating_financial_materiality": round(min(fin_sig / 20.0, 1.0) * 10, 1),
        "rating_india_relevance": round(india_relevance / 10.0, 1),
        "rating_freshness": round(freshness_bonus, 1),
        "rating_source_quality": round(source_base_score / 10.0, 1),
        "rating_investor_relevance": round(min((aud_interest + disc_potential) / 30.0, 1.0) * 10, 1),
    }

    return importance_score, postability_score, confidence_score, final_score, breakdown
