import logging
from typing import List
from app.research.models import Fact, ConflictAlert, SourceDetails

logger = logging.getLogger(__name__)

def calculate_research_confidence(
    sources: List[SourceDetails], 
    facts: List[Fact], 
    conflicts: List[ConflictAlert]
) -> int:
    """
    Computes a research confidence score from 0 to 100 based on:
    - Source priority/quality.
    - Quantity of independent publications (more confirmation = higher trust).
    - Presence of official announcements or filings.
    - Disagreement/conflict counts.
    - Quantity of extracted facts.
    """
    if not sources:
        return 0

    score = 0.0

    # 1. Base Source Quality (Max 30 pts)
    # Average priority score (which ranges 40 to 100) scaled to 30
    avg_priority = sum(s.priority for s in sources) / len(sources)
    score += (avg_priority / 100.0) * 30.0

    # 2. Source Diversity (Max 30 pts)
    # Confirmation by multiple independent domains
    num_sources = len(sources)
    if num_sources == 1:
        score += 10.0
    elif num_sources == 2:
        score += 20.0
    else:
        score += 30.0

    # 3. Official / Primary Source Presence (Max 15 pts)
    # Check if any source matches official filings or announcements
    has_primary = False
    for src in sources:
        src_name = src.source_name.lower()
        if any(keyword in src_name for keyword in ["sebi", "rbi", "filing", "official", "announcement", "release", "press"]):
            has_primary = True
            break
    if has_primary:
        score += 15.0

    # 4. Fact Abundance (Max 15 pts)
    # If we extracted multiple distinct facts, it represents a rich report
    num_facts = len(facts)
    if num_facts >= 3:
        score += 15.0
    elif num_facts > 0:
        score += 8.0

    # 5. Verification Consensus (Max 10 pts)
    # If multiple facts were cross-source verified (confidence = 1.0)
    has_verified = any(f.confidence >= 1.0 for f in facts)
    if has_verified:
        score += 10.0

    # 6. Conflict Penalties
    # Unresolved conflicts deduct confidence points
    open_conflicts = [c for c in conflicts if c.status == "OPEN"]
    for conflict in open_conflicts:
        if conflict.severity == "HIGH":
            score -= 25.0
        else:
            score -= 10.0

    # Bounds check
    final_score = int(round(score))
    return max(0, min(100, final_score))
