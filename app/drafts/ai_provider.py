"""
AI-assisted draft generation, through the existing AI_PROVIDER/Ollama
config scaffold (app/config.py) — previously unused by any code path.

Design constraints from the project brief, enforced here directly:
- Never a hard dependency: AI_PROVIDER defaults to "none", and production
  (Vercel) has no Ollama to reach, so this must fail closed and fast.
- No paid API: only a local Ollama HTTP call, using the `requests` library
  already in requirements.txt — no new dependency.
- Strict timeout so a slow/unreachable host can't hang a cron job.
- The caller (drafts/engine.py) always re-runs the same quality/fact-safety
  checks on AI output as on deterministic output — this module does not get
  to skip QC just because it's "AI".
"""
import json
import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 8


def is_ai_configured() -> bool:
    return settings.AI_PROVIDER == "ollama" and bool(settings.OLLAMA_HOST) and bool(settings.OLLAMA_MODEL)


def _build_prompt(intel_summary: str, tweet_limit: int) -> str:
    return (
        "You write a single X (Twitter) post about an Indian stock-market/business event "
        "for a finance-savvy audience. Rules, no exceptions:\n"
        "1. Use ONLY the facts given below. Never invent a number, quote, name, or outcome.\n"
        "2. Do not just restate the headline — add a hook and explain why it matters.\n"
        f"3. Stay under {tweet_limit} characters. Plain text only, no hashtags, no markdown.\n"
        "4. If a figure is uncertain or missing, omit it rather than guessing.\n\n"
        f"FACTS:\n{intel_summary}\n\nWrite only the post text, nothing else."
    )


def generate_with_ai(intel_summary: str, tweet_limit: int = 280, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> Optional[str]:
    """
    Calls a local Ollama instance to draft a post grounded in intel_summary.
    Returns None on any failure (unreachable host, timeout, empty/malformed
    response) so the caller falls back to the deterministic hook engine —
    this function is never allowed to raise out to a caller.
    """
    if not is_ai_configured():
        return None

    try:
        import requests
    except ImportError:
        return None

    prompt = _build_prompt(intel_summary, tweet_limit)
    url = f"{settings.OLLAMA_HOST.rstrip('/')}/api/generate"

    try:
        response = requests.post(
            url,
            json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        if response.status_code != 200:
            logger.warning(f"AI drafting: Ollama returned HTTP {response.status_code}, falling back to deterministic path.")
            return None
        data = response.json()
        text = (data.get("response") or "").strip()
        if not text:
            return None
        return text
    except Exception as e:
        logger.warning(f"AI drafting: Ollama call failed ({e}), falling back to deterministic path.")
        return None


def build_intel_summary(story, intel) -> str:
    """Renders the structured intelligence into a compact, factual prompt block — no prose, just facts."""
    lines = [
        f"Company: {intel.company or 'Unknown'}",
        f"Event type: {intel.event_type}",
        f"Headline: {story.title}",
    ]
    if intel.key_numbers:
        for f in intel.key_numbers:
            lines.append(f"Fact - {f.fact_type}: {f.original_value} (confidence: {f.confidence})")
    if intel.why_it_matters:
        lines.append(f"Why it matters (research analyst note): {intel.why_it_matters}")
    lines.append(f"Market impact so far: {intel.market_impact}")
    lines.append(f"Source confidence: {intel.source_confidence_label}")
    if intel.disputed_fact_types:
        lines.append(f"Disputed/unconfirmed figures (do not state as fact): {', '.join(intel.disputed_fact_types)}")
    return "\n".join(lines)
