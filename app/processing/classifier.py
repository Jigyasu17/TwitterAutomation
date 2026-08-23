import re
import json
import logging
from typing import Dict, List, Tuple, Any

logger = logging.getLogger(__name__)

# Predefined dictionary for entity extraction
KNOWN_COMPANIES = {
    "tata motors", "tata", "reliance", "jio", "infosys", "wipro", "hdfc", "sbi", 
    "navi", "zepto", "zomato", "paytm", "adani", "ather energy", "ather", "ola", 
    "lic", "rbi", "sebi", "bse", "nse", "makemytrip", "cult.fit", "cultfit", 
    "biocon", "lohia corp", "sembcorp", "carlsberg", "manipal health", "l&t", 
    "infy", "air india", "indigo", "tcs", "byjus", "physics wallah", "swiggy",
    "google", "apple", "microsoft", "amazon", "tesla", "nvidia", "reuters", "bloomberg"
}

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

# Source Priority Configurations (configurable trust mappings)
SOURCE_PRIORITIES = {
    "sebi": 100,
    "rbi": 100,
    "bse": 95,
    "nse": 95,
    "reuters": 90,
    "bloomberg": 90,
    "economic times": 85,
    "moneycontrol": 85,
    "business standard": 85,
    "financial times": 85,
    "techcrunch": 80,
    "yourstory": 75,
    "general": 60
}

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
    if any(k in text for k in ["ipo", "drhp", "draft papers", "listing day", "listings", "public issue"]):
        primary = "IPO"
        if "sebi" in text: secondary_tags.append("REGULATORY")
        if "gmp" in text or "premium" in text: secondary_tags.append("MARKET")
        return primary, list(set(secondary_tags))
        
    # 2. FUNDING
    if any(k in text for k in ["raises", "funding round", "series a", "series b", "series c", "seed funding", "venture capital", "raised $", "raised ₹"]):
        primary = "FUNDING"
        secondary_tags.append("STARTUP")
        if "fintech" in text: secondary_tags.append("FINTECH")
        return primary, list(set(secondary_tags))
        
    # 3. M&A
    if any(k in text for k in ["acquisition", "acquires", "merger", "buyout", "takeover", "merges with"]):
        primary = "M&A"
        if "deal" in text: secondary_tags.append("BUSINESS")
        return primary, list(set(secondary_tags))
        
    # 4. REGULATORY
    if any(k in text for k in ["rbi", "sebi", "mca", "regulatory", "penalty", "sebi bars", "rbi imposes", "compliance", "notice"]):
        primary = "REGULATORY"
        if "bank" in text or "fintech" in text: secondary_tags.append("FINANCE")
        return primary, list(set(secondary_tags))
        
    # 5. MARKET
    if any(k in text for k in ["sensex", "nifty", "bull run", "stock market", "indices", "nasdaq", "bse", "nse", "global markets"]):
        primary = "MARKET"
        if "shares" in text: secondary_tags.append("STOCK")
        return primary, list(set(secondary_tags))

    # 6. STOCK
    if any(k in text for k in ["dividend", "bonus issue", "stock split", "shares jump", "shares fall", "shares rally", "ticker"]):
        primary = "STOCK"
        secondary_tags.append("MARKET")
        return primary, list(set(secondary_tags))

    # 7. ECONOMY
    if any(k in text for k in ["gdp", "inflation", "cpi", "fiscal deficit", "tax collection", "gst", "economic growth", "interest rates"]):
        primary = "ECONOMY"
        if "rbi" in text: secondary_tags.append("REGULATORY")
        return primary, list(set(secondary_tags))
        
    # 8. STARTUP
    if any(k in text for k in ["startup", "unicorn", "founder", "incubator", "y combinator"]):
        primary = "STARTUP"
        if "funding" in text or "round" in text: secondary_tags.append("FUNDING")
        return primary, list(set(secondary_tags))

    # 9. TECH
    if any(k in text for k in ["semiconductor", "ai", "artificial intelligence", "software", "chip", "robotics", "ev", "electric vehicle"]):
        primary = "TECH"
        if "ev" in text: secondary_tags.append("EV")
        if "ai" in text: secondary_tags.append("AI")
        return primary, list(set(secondary_tags))

    # 10. GLOBAL
    if any(k in text for k in ["fed hike", "us inflation", "china economy", "opec", "global oil", "eurozone"]):
        primary = "GLOBAL"
        secondary_tags.append("ECONOMY")
        return primary, list(set(secondary_tags))

    # 11. BUSINESS (Capex / Expansion / Corporate announcements)
    if any(k in text for k in ["capex", "investment", "factory", "manufacturing", "announces", "plans to invest", "expansion", "jv"]):
        primary = "BUSINESS"
        if "ev" in text: secondary_tags.append("TECH")
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
    if "ipo listing" in t or "lists at" in t or "debuts" in t or "listing" in t:
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
        "Countries": []
    }
    
    # 1. Match known companies dictionary
    for company in KNOWN_COMPANIES:
        # Match as a whole word boundary
        if re.search(r'\b' + re.escape(company) + r'\b', text_lower):
            # Title case it for styling
            name = company.upper() if company in ["rbi", "sebi", "bse", "nse", "lic", "tcs", "l&t", "infy"] else company.title()
            extracted["Companies"].append(name)
            
    # Heuristic dynamic company extraction: Look for capitalized word phrases preceding action verbs
    # E.g. "[Zepto] plans to file..." or "[Tata Motors] announces..."
    action_verbs = r'(?:raises|invests|reports|announces|launches|files|plans|debuts|lists|unveils|partners|acquires|merges|hires|eyes|seeks)'
    company_regex = r'\b([A-Z][a-zA-Z0-9&]*(?:\s+[A-Z][a-zA-Z0-9&]*)*)\s+' + action_verbs
    matches = re.findall(company_regex, title)
    for match in matches:
        match_clean = match.strip()
        # Filter out common false positives (days of week, stopwords)
        if match_clean not in {"SEBI", "RBI", "India", "US", "IPO", "GMP", "Sensex", "Nifty", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}:
            if match_clean not in extracted["Companies"]:
                # Check if it contains a known lowercase match first to avoid duplicate representations
                if match_clean.lower() not in [c.lower() for c in extracted["Companies"]]:
                    extracted["Companies"].append(match_clean)

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

def calculate_scores(
    title: str, 
    summary: str, 
    source_name: str, 
    source_count: int = 1
) -> Tuple[int, int, int, int, Dict[str, Any]]:
    """
    Computes rule-based scores (0-100) for Importance, Postability, and Confidence.
    Returns:
        Tuple: (importance_score, postability_score, confidence_score, final_score, score_breakdown)
    """
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
        elif "million" in text or "crore" in text or "cr" in text: fin_sig = 10
        
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
    elif any(k in text for k in ["ev", "electric vehicle", "ai", "semiconductor", "stock market", "inflation"]):
        aud_interest = 11
        
    # 5. Discussion Potential (Max 15)
    disc_potential = 5
    # Things that spark opinions/debate: policy rates, layoffs, startup valuations, bans, losses
    if any(k in text for k in ["layoff", "job cuts", "ban", "loss", "valuation drops", "valuation cut", "rate hike", "tax", "gst"]):
        disc_potential = 13
    elif any(k in text for k in ["ipo pricing", "valuing at", "investment"]):
        disc_potential = 10
        
    # 6. Source Confidence (Max 10)
    source_key = clean_and_lower(source_name)
    source_base_score = 60
    for key, weight in SOURCE_PRIORITIES.items():
        if key in source_key:
            source_base_score = weight
            break
    # Map 0-100 source score to 0-10 subscore
    source_confidence_sub = int(source_base_score / 10)
    
    # Total Importance (sum of all subscores)
    importance_score = market_impact + fin_sig + novelty + aud_interest + disc_potential + source_confidence_sub
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
    
    breakdown = {
        "market_impact": market_impact,
        "financial_significance": fin_sig,
        "novelty": novelty,
        "audience_interest": aud_interest,
        "discussion_potential": disc_potential,
        "source_confidence_sub": source_confidence_sub
    }
    
    return importance_score, postability_score, confidence_score, final_score, breakdown
