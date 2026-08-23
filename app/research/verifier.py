import logging
from typing import List, Dict, Tuple, Any
from app.research.models import Fact, ConflictAlert, SourceDetails

logger = logging.getLogger(__name__)

def verify_facts(
    facts: List[Fact], 
    sources_map: Dict[int, SourceDetails]
) -> Tuple[List[Fact], List[ConflictAlert]]:
    """
    Compares facts of the same type across different sources.
    - Groups facts by type.
    - If facts of the same type differ by > 5% (numeric values) or differ exactly (non-numeric ranges),
      it flags them as a conflict.
    - If they match, it compiles a verified consensus fact with elevated confidence.
    """
    grouped_facts: Dict[str, List[Fact]] = {}
    for fact in facts:
        grouped_facts.setdefault(fact.fact_type, []).append(fact)
        
    verified_facts: List[Fact] = []
    conflicts: List[ConflictAlert] = []

    for fact_type, fact_list in grouped_facts.items():
        if len(fact_list) == 1:
            # Only one source reported this fact - it's verified by default but with standard confidence
            verified_facts.append(fact_list[0])
            continue

        # We have multiple sources reporting this fact type
        has_conflict = False
        primary_fact = fact_list[0]
        
        # Check pairwise conflicts
        for i in range(len(fact_list)):
            for j in range(i + 1, len(fact_list)):
                fact_a = fact_list[i]
                fact_b = fact_list[j]
                
                source_a_name = sources_map.get(fact_a.source_id).source_name if fact_a.source_id in sources_map else "Unknown Source"
                source_b_name = sources_map.get(fact_b.source_id).source_name if fact_b.source_id in sources_map else "Unknown Source"
                
                # Check match
                is_match = False
                val_a = fact_a.normalized_value
                val_b = fact_b.normalized_value
                
                if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                    # Numeric tolerance check (within 5% range)
                    if max(val_a, val_b) > 0:
                        diff_ratio = abs(val_a - val_b) / max(val_a, val_b)
                        if diff_ratio <= 0.05:
                            is_match = True
                    else:
                        is_match = True
                else:
                    # String/range exact check
                    if str(val_a).strip() == str(val_b).strip():
                        is_match = True

                if not is_match:
                    has_conflict = True
                    severity = "HIGH" if fact_type in {"funding_amount", "valuation", "acquisition_value", "ipo_size", "profit", "revenue", "loss"} else "MEDIUM"
                    
                    conflict = ConflictAlert(
                        conflict_type="VALUE_MISMATCH",
                        fact_type=fact_type,
                        source_a=source_a_name,
                        value_a=fact_a.original_value,
                        source_b=source_b_name,
                        value_b=fact_b.original_value,
                        severity=severity,
                        status="OPEN"
                    )
                    conflicts.append(conflict)
                    
        if not has_conflict:
            # All sources agree - take the one from the highest priority source or just the first one
            # Boost confidence because of cross-source consensus verification!
            consensus_fact = Fact(
                fact_type=primary_fact.fact_type,
                original_value=primary_fact.original_value,
                normalized_value=primary_fact.normalized_value,
                currency=primary_fact.currency,
                unit=primary_fact.unit,
                confidence=1.0, # Multi-source consensus gives maximum confidence
                context=primary_fact.context,
                source_id=primary_fact.source_id
            )
            verified_facts.append(consensus_fact)
        else:
            # Discrepancies exist. Still add the primary fact for drafting reference, but it is flagged in conflicts
            verified_facts.extend(fact_list)

    return verified_facts, conflicts
