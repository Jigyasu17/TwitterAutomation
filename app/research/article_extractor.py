import re
import time
import logging
import requests
import trafilatura
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Optional

logger = logging.getLogger(__name__)

# Domain delay tracking for rate limiting (in-memory within single run queue)
_last_request_times = {}

def extract_article_content(
    url: str, 
    request_delay_seconds: float = 1.0, 
    timeout_seconds: int = 10
) -> Optional[str]:
    """
    Downloads and extracts the clean body text of an article.
    - Implements domain-based rate-limiting delays.
    - Utilizes trafilatura for primary main-content extraction.
    - Falls back to a tailored BeautifulSoup parser if trafilatura fails.
    """
    if not url:
        return None

    # --- 1. Rate Limiting ---
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    now = time.time()
    if domain in _last_request_times:
        time_elapsed = now - _last_request_times[domain]
        if time_elapsed < request_delay_seconds:
            sleep_time = request_delay_seconds - time_elapsed
            logger.debug(f"Rate limiting domain '{domain}': Sleeping for {sleep_time:.2f} seconds.")
            time.sleep(sleep_time)
            
    _last_request_times[domain] = time.time()

    # --- 2. Fetch HTML Content ---
    logger.info(f"Fetching article content from: {url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=timeout_seconds)
        if response.status_code != 200:
            logger.error(f"Failed to fetch source: HTTP {response.status_code} for URL {url}")
            return None
            
        html_content = response.text
        
        # --- 3. Extract Text via Trafilatura ---
        extracted_text = trafilatura.extract(html_content)
        
        # --- 4. Fallback to BeautifulSoup ---
        if not extracted_text:
            logger.warning(f"Trafilatura extraction returned empty content. Falling back to BeautifulSoup parser for {url}")
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Decompose boilerplate tags
            for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                element.decompose()
                
            # Attempt to target common content wrapper containers
            content_area = soup.find("article") or soup.find("main") or soup.find("div", {"class": re.compile(r"content|body|article", re.I)})
            if not content_area:
                content_area = soup.body
                
            if content_area:
                paragraphs = content_area.find_all("p")
                if paragraphs:
                    extracted_text = "\n\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
                else:
                    extracted_text = content_area.get_text(separator="\n")
                    
            if extracted_text:
                # Clean trailing lines
                lines = [line.strip() for line in extracted_text.split("\n") if line.strip()]
                extracted_text = "\n".join(lines)
                
        return extracted_text

    except Exception as e:
        logger.error(f"Error fetching/extracting article text from '{url}': {e}", exc_info=True)
        return None
