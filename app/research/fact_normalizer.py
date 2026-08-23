import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def parse_monetary_value(value_str: str) -> Optional[Tuple[float, str]]:
    """
    Parses a string-based currency value and standardizes it:
    Returns (normalized_value_float, currency_code_str) or None.
    Examples:
    - "$100 million" -> (100000000.0, "USD")
    - "Rs 500 Cr" -> (5000000000.0, "INR")
    - "₹5,000 crore" -> (50000000000.0, "INR")
    - "INR 10B" -> (10000000000.0, "INR")
    """
    if not value_str:
        return None

    clean_str = value_str.lower().replace(",", "").strip()

    # 1. Identify Currency
    currency = "INR"  # Default fallback if Indian context
    if "$" in clean_str or "usd" in clean_str or "dollar" in clean_str:
        currency = "USD"
    elif "₹" in clean_str or "rs" in clean_str or "inr" in clean_str or "rupee" in clean_str:
        currency = "INR"

    # 2. Extract numeric digits
    # Matches decimals or integers: e.g., 100, 50.5, 5,000
    num_match = re.search(r'(\d+(?:\.\d+)?)', clean_str)
    if not num_match:
        return None
        
    val = float(num_match.group(1))

    # 3. Apply multipliers
    multiplier = 1.0
    if "billion" in clean_str or re.search(r'\b(b)\b', clean_str):
        multiplier = 1_000_000_000.0
    elif "million" in clean_str or re.search(r'\b(m)\b', clean_str):
        multiplier = 1_000_000.0
    elif "crore" in clean_str or "cr" in clean_str:
        multiplier = 10_000_000.0
    elif "lakh" in clean_str or "l" in clean_str:
        multiplier = 100_000.0
    elif "k" in clean_str:
        multiplier = 1_000.0

    return val * multiplier, currency

def normalize_percentage(value_str: str) -> Optional[float]:
    """
    Parses a percentage string and standardizes it to a float.
    - "12.5%" -> 12.5
    - "8 percent" -> 8.0
    """
    if not value_str:
        return None
    clean_str = value_str.lower().replace("%", "").replace("percent", "").strip()
    num_match = re.search(r'(\d+(?:\.\d+)?)', clean_str)
    if num_match:
        return float(num_match.group(1))
    return None
