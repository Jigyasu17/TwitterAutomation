import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Stopwords set to optimize keyword indexing and title hashes
STOPWORDS = {
    "a", "an", "the", "is", "on", "at", "for", "with", "by", "to", "in", "of",
    "and", "that", "this", "it", "from", "as", "are", "was", "were", "be",
    "been", "has", "have", "had", "do", "does", "did", "about", "into", "through"
}

def normalize_url(url: str) -> str:
    """
    Cleans up a URL to prevent duplicate listings under slight tracking query variations:
    - Lowercases the hostname
    - Filters tracking parameters (e.g., utm_*, ref, source, sys_id, gclid, fbclid)
    - Strips fragments (#anchor)
    - Removes trailing slashes on the path
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        # Normalize hostname (lowercase)
        netloc = parsed.netloc.lower()
        
        # Parse query params and filter tracking keys
        query_params = parse_qsl(parsed.query)
        filtered_params = [
            (k, v) for k, v in query_params
            if not k.lower().startswith("utm_") and 
            k.lower() not in {"ref", "source", "sys_id", "click_id", "fbclid", "gclid", "campaign"}
        ]
        
        # Reconstruct path without trailing slash (unless it is just a single slash)
        path = parsed.path
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
            
        # Reconstruct URL components
        new_query = urlencode(filtered_params)
        new_parsed = parsed._replace(
            netloc=netloc,
            path=path,
            query=new_query,
            fragment=""
        )
        return urlunparse(new_parsed)
    except Exception:
        # Fallback to the original URL if parsing fails
        return url

def clean_text(text: str, remove_stopwords: bool = False) -> str:
    """
    Standard text normalization:
    - Casing: lowercase
    - Punctuation: removes special chars except alphanumeric and spaces
    - Whitespace: collapses multiple spaces
    - Stopwords: (optional) filters out common small words
    """
    if not text:
        return ""
    
    # Lowercase
    cleaned = text.lower()
    # Strip punctuation/special characters
    cleaned = re.sub(r'[^a-z0-9\s]', '', cleaned)
    # Collapse multiple whitespaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    if remove_stopwords:
        tokens = cleaned.split()
        filtered_tokens = [t for t in tokens if t not in STOPWORDS]
        cleaned = " ".join(filtered_tokens)
        
    return cleaned
