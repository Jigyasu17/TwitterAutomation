import logging
from typing import List, Dict
from app.domain.models import StoryData, ResearchFactData, ResearchConflictData, ResearchSourceData

logger = logging.getLogger(__name__)

def generate_why_it_matters(event_type: str, company: str) -> str:
    """Generates a deterministic significance statement based on the corporate event type."""
    comp_ref = company if company else "The entity"
    
    mapping = {
        "FUNDING": f"This capital infusion provides {comp_ref} with immediate runway, supporting scaling, hiring, and expansion operations.",
        "INVESTMENT": f"Strategic investments validate {comp_ref}'s market fit and signal backing from sophisticated financial allocators.",
        "IPO_FILING": f"Filing draft papers for a public debut transitions {comp_ref} toward high regulatory scrutiny and opens liquidity channels for early backers.",
        "IPO_LISTING": f"Listing on public exchanges provides retail access and marks a critical maturity phase for {comp_ref}'s capitalization table.",
        "ACQUISITION": f"Consolidating operations through acquisition alters market dynamics and expands the acquirer's product portfolio or customer reach.",
        "MERGER": "Mergers combine operational capacities and synergies, aiming for cost efficiencies and combined market footprint.",
        "PROFIT_UPDATE": f"Stronger profit performance indicates operational efficiency, improving cash flows and bolstering investor confidence in {comp_ref}.",
        "LOSS_UPDATE": f"Widening losses highlight cash burn or developmental phases, necessitating strict capital management by {comp_ref}.",
        "REGULATORY_ACTION": "SEBI/RBI regulatory oversight ensures retail protection and market integrity, though it may trigger governance or compliance overheads.",
        "PRODUCT_LAUNCH": f"Releasing new products signals active R&D and marks entry into adjacent competitive segments for {comp_ref}.",
        "EXECUTIVE_CHANGE": "Leadership transitions introduce new management philosophies and strategy directions for corporate governance.",
    }
    
    return mapping.get(event_type, "This development indicates strategic movements within the company's operating sector and triggers adjacent industry ripples.")

def build_research_report(
    story: StoryData,
    sources: List[ResearchSourceData],
    facts: List[ResearchFactData],
    conflicts: List[ResearchConflictData],
    confidence_score: int
) -> str:
    """
    Compiles a highly structured research report in Markdown.
    """
    lines = []
    
    # 1. Title
    lines.append(f"# Research Report: {story.title}")
    lines.append("")

    # 2. What Happened
    lines.append("## WHAT HAPPENED")
    lines.append(story.summary or f"Reports indicate that {story.title}. This event has been tracked and analyzed across multiple news publications.")
    lines.append("")

    # 3. Key Facts
    lines.append("## KEY FACTS")
    lines.append(f"- **Primary Company**: {story.company or 'Generic'}")
    lines.append(f"- **Category**: {story.category}")
    lines.append(f"- **Event Action**: {story.event_type or 'OTHER'}")
    lines.append("")

    # 4. Important Numbers
    lines.append("## IMPORTANT NUMBERS")
    numeric_facts = [f for f in facts if f.fact_type in {"funding_amount", "valuation", "acquisition_value", "ipo_size", "revenue", "profit", "loss", "ipo_price_band", "stock_movement", "subscription_number"}]
    if numeric_facts:
        for fact in numeric_facts:
            unit_lbl = f" {fact.unit}" if fact.unit not in {"absolute", "range"} else ""
            lines.append(f"- **{fact.fact_type.replace('_', ' ').title()}**: {fact.original_value} (Normalized: {fact.normalized_value}{unit_lbl})")
    else:
        lines.append("- *No numerical metrics confidently isolated from body content.*")
    lines.append("")

    # 5. Entities Extracted
    lines.append("## ENTITIES")
    entities = story.entities or {}
    companies = entities.get("Companies", [])
    sectors = entities.get("Sectors", [])
    countries = entities.get("Countries", [])
    
    lines.append(f"- **Companies**: {', '.join(companies) if companies else 'None identified'}")
    lines.append(f"- **Sectors**: {', '.join(sectors) if sectors else 'None identified'}")
    lines.append(f"- **Countries**: {', '.join(countries) if countries else 'Global'}")
    lines.append("")

    # 6. Why it Matters
    lines.append("## WHY IT MATTERS")
    lines.append(generate_why_it_matters(story.event_type or "OTHER", story.company))
    lines.append("")

    # 7. Source Verification
    lines.append("## SOURCE VERIFICATION")
    lines.append("We evaluated and cross-checked the following sources:")
    for idx, src in enumerate(sources, 1):
        lines.append(f"{idx}. **[{src.source_name}]**: {src.title}")
        lines.append(f"   - URL: {src.url}")
        lines.append(f"   - Priority Rating: {src.priority}/100 (Extraction Status: {src.extraction_status})")
    lines.append("")

    # 8. Conflicts Log
    lines.append("## CONFLICTS DETECTED")
    open_conflicts = [c for c in conflicts if c.status == "OPEN"]
    if open_conflicts:
        lines.append("> [!WARNING]")
        lines.append("> Fact discrepancies detected between publishers. Manual verification required.")
        lines.append("")
        for conflict in open_conflicts:
            lines.append(f"- **{conflict.fact_type.replace('_', ' ').upper()} Discrepancy ({conflict.severity} Severity)**:")
            lines.append(f"  - **{conflict.source_a}** reports: `{conflict.value_a}`")
            lines.append(f"  - **{conflict.source_b}** reports: `{conflict.value_b}`")
    else:
        lines.append("- *No high-severity fact conflicts detected. Publications are in alignment.*")
    lines.append("")

    # 9. Research Confidence
    lines.append("## RESEARCH CONFIDENCE")
    lines.append(f"**Confidence Rating: {confidence_score}/100**")
    lines.append("")
    if confidence_score >= 80:
        lines.append("This report has HIGH confidence due to consensus agreement across reputable sources.")
    elif confidence_score >= 50:
        lines.append("This report has MEDIUM confidence. Sources are generally reliable, but metrics may represent secondary reporting.")
    else:
        lines.append("This report has LOW confidence. Verify core numbers manually before drafting content.")
        
    return "\n".join(lines)
