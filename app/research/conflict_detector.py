import logging
from typing import List, Dict
from app.research.models import Fact, ConflictAlert, SourceDetails
from app.research.verifier import verify_facts

logger = logging.getLogger(__name__)

def find_fact_conflicts(
    facts: List[Fact], 
    sources_map: Dict[int, SourceDetails]
) -> List[ConflictAlert]:
    """
    Scans list of facts and returns any detected conflict alerts.
    """
    _, conflicts = verify_facts(facts, sources_map)
    return conflicts
