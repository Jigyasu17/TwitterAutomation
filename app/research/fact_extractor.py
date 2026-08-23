import re
import logging
from typing import List, Optional
from app.research.models import Fact
from app.research.fact_normalizer import parse_monetary_value, normalize_percentage

logger = logging.getLogger(__name__)

# Currency regex pattern
CURRENCY_PATTERN = r'((?:\$|₹|inr|rs|usd)\s*\d+(?:\.\d+)?\s*(?:billion|million|crore|cr|m|b)?\b|\b\d+(?:\.\d+)?\s*(?:crore|cr|million|billion)\b)'

# Percentage regex pattern
PERCENT_PATTERN = r'(\d+(?:\.\d+)?\s*(?:%|percent))'

# Subscription times regex pattern
SUB_PATTERN = r'\b(\d+(?:\.\d+)?\s*(?:times|x))\b'

def split_into_sentences(text: str) -> List[str]:
    """Splits article text into clean sentences."""
    if not text:
        return []
    # Split on sentence boundaries (. ! ?) followed by whitespace
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def extract_facts_from_text(text: str, source_id: Optional[int] = None) -> List[Fact]:
    """
    Scans the article text sentence by sentence to extract structured facts:
    - funding_amount
    - valuation
    - acquisition_value
    - ipo_size
    - ipo_price_band
    - stock_movement
    - subscription_number
    - revenue / profit / loss
    """
    facts = []
    sentences = split_into_sentences(text)
    
    seen_facts = set() # To prevent duplicate facts from the same source
    
    for sentence in sentences:
        sentence_lower = sentence.lower()
        
        # --- 1. Funding Amount ---
        if any(k in sentence_lower for k in ["raises", "raised", "funding round", "seed round", "series a", "series b", "series c", "raised capital"]):
            match = re.search(CURRENCY_PATTERN, sentence_lower)
            if match:
                original = match.group(1)
                parsed = parse_monetary_value(original)
                if parsed:
                    val, curr = parsed
                    fact = Fact(
                        fact_type="funding_amount",
                        original_value=original,
                        normalized_value=val,
                        currency=curr,
                        confidence=0.90,
                        context=sentence[:250],
                        source_id=source_id
                    )
                    fact_key = ("funding_amount", val, curr)
                    if fact_key not in seen_facts:
                        seen_facts.add(fact_key)
                        facts.append(fact)

        # --- 2. Valuation ---
        if any(k in sentence_lower for k in ["valuation", "valued at", "value of", "worth"]):
            match = re.search(CURRENCY_PATTERN, sentence_lower)
            if match:
                original = match.group(1)
                parsed = parse_monetary_value(original)
                if parsed:
                    val, curr = parsed
                    fact = Fact(
                        fact_type="valuation",
                        original_value=original,
                        normalized_value=val,
                        currency=curr,
                        confidence=0.90,
                        context=sentence[:250],
                        source_id=source_id
                    )
                    fact_key = ("valuation", val, curr)
                    if fact_key not in seen_facts:
                        seen_facts.add(fact_key)
                        facts.append(fact)

        # --- 3. Acquisition Value ---
        if any(k in sentence_lower for k in ["acquired for", "acquisition for", "merger value", "buys for", "takeover of"]):
            match = re.search(CURRENCY_PATTERN, sentence_lower)
            if match:
                original = match.group(1)
                parsed = parse_monetary_value(original)
                if parsed:
                    val, curr = parsed
                    fact = Fact(
                        fact_type="acquisition_value",
                        original_value=original,
                        normalized_value=val,
                        currency=curr,
                        confidence=0.95,
                        context=sentence[:250],
                        source_id=source_id
                    )
                    fact_key = ("acquisition_value", val, curr)
                    if fact_key not in seen_facts:
                        seen_facts.add(fact_key)
                        facts.append(fact)

        # --- 4. IPO Size ---
        if "ipo" in sentence_lower and any(k in sentence_lower for k in ["size", "aims to raise", "public issue", "plan to raise", "target"]):
            match = re.search(CURRENCY_PATTERN, sentence_lower)
            if match:
                original = match.group(1)
                parsed = parse_monetary_value(original)
                if parsed:
                    val, curr = parsed
                    fact = Fact(
                        fact_type="ipo_size",
                        original_value=original,
                        normalized_value=val,
                        currency=curr,
                        confidence=0.90,
                        context=sentence[:250],
                        source_id=source_id
                    )
                    fact_key = ("ipo_size", val, curr)
                    if fact_key not in seen_facts:
                        seen_facts.add(fact_key)
                        facts.append(fact)

        # --- 5. IPO Price Band ---
        if any(k in sentence_lower for k in ["price band", "price range", "ipo price", "pricing"]):
            # Look for price ranges like "Rs 500 to Rs 520" or "Rs 500 - 520"
            range_match = re.search(r'(?:rs|₹|inr)?\s*(\d+)\s*(?:to|-)\s*(?:rs|₹|inr)?\s*(\d+)', sentence_lower)
            if range_match:
                original = range_match.group(0)
                val_a = float(range_match.group(1))
                val_b = float(range_match.group(2))
                fact = Fact(
                    fact_type="ipo_price_band",
                    original_value=original,
                    normalized_value=f"{val_a}-{val_b}",
                    unit="range",
                    confidence=0.95,
                    context=sentence[:250],
                    source_id=source_id
                )
                fact_key = ("ipo_price_band", f"{val_a}-{val_b}", None)
                if fact_key not in seen_facts:
                    seen_facts.add(fact_key)
                    facts.append(fact)

        # --- 6. Stock Movement ---
        if any(k in sentence_lower for k in ["shares", "stock", "nifty", "sensex"]) and any(k in sentence_lower for k in ["jump", "surge", "gain", "rise", "fall", "drop", "plunge", "slide", "slip", "down"]):
            match = re.search(PERCENT_PATTERN, sentence_lower)
            if match:
                original = match.group(1)
                val = normalize_percentage(original)
                if val is not None:
                    # Determine direction (jump/surge/rise = positive; fall/drop/plunge = negative)
                    direction = -1.0 if any(k in sentence_lower for k in ["fall", "drop", "plunge", "slide", "slip", "down", "lower"]) else 1.0
                    fact = Fact(
                        fact_type="stock_movement",
                        original_value=original,
                        normalized_value=val * direction,
                        unit="percentage",
                        confidence=0.85,
                        context=sentence[:250],
                        source_id=source_id
                    )
                    fact_key = ("stock_movement", val * direction, None)
                    if fact_key not in seen_facts:
                        seen_facts.add(fact_key)
                        facts.append(fact)

        # --- 7. Subscription Number ---
        if any(k in sentence_lower for k in ["subscribed", "subscription", "bid", "bids"]):
            match = re.search(SUB_PATTERN, sentence_lower)
            if match:
                original = match.group(1)
                num_match = re.search(r'(\d+(?:\.\d+)?)', original.lower())
                if num_match:
                    val = float(num_match.group(1))
                    fact = Fact(
                        fact_type="subscription_number",
                        original_value=original,
                        normalized_value=val,
                        unit="times",
                        confidence=0.95,
                        context=sentence[:250],
                        source_id=source_id
                    )
                    fact_key = ("subscription_number", val, None)
                    if fact_key not in seen_facts:
                        seen_facts.add(fact_key)
                        facts.append(fact)

        # --- 8. Revenue / Profit / Loss ---
        if any(k in sentence_lower for k in ["revenue", "profit", "net income", "loss", "sales"]):
            match = re.search(CURRENCY_PATTERN, sentence_lower)
            if match:
                original = match.group(1)
                parsed = parse_monetary_value(original)
                if parsed:
                    val, curr = parsed
                    # Determine subtype
                    fact_type = "revenue"
                    if "profit" in sentence_lower or "net income" in sentence_lower:
                        fact_type = "profit"
                    elif "loss" in sentence_lower:
                        fact_type = "loss"
                        
                    fact = Fact(
                        fact_type=fact_type,
                        original_value=original,
                        normalized_value=val,
                        currency=curr,
                        confidence=0.90,
                        context=sentence[:250],
                        source_id=source_id
                    )
                    fact_key = (fact_type, val, curr)
                    if fact_key not in seen_facts:
                        seen_facts.add(fact_key)
                        facts.append(fact)
                        
    return facts
