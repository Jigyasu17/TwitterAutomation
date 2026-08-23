import logging
import hashlib
from datetime import datetime
from typing import Any, Optional
from app.domain.models import StoryData, ResearchReportData, ResearchSourceData, ResearchFactData, ResearchConflictData
from app.repositories.interfaces import StoryRepository, ResearchRepository
from app.research.source_discovery import discover_sources
from app.research.article_extractor import extract_article_content
from app.research.fact_extractor import extract_facts_from_text
from app.research.verifier import verify_facts
from app.research.scorer import calculate_research_confidence
from app.research.report_builder import build_research_report, generate_why_it_matters

logger = logging.getLogger(__name__)

def research_story(*args, **kwargs) -> str:
    """
    Orchestrates the entire research pipeline for a single story.
    Supports signature overloads:
      1. research_story(db, story_id, force_rerun=False)
      2. research_story(story_repo, research_repo, story_id, force_rerun=False)
    """
    story_repo = args[0] if len(args) >= 1 else kwargs.get("story_repo")
    
    # Detect legacy database Session vs Repository interface
    is_legacy = story_repo is not None and not hasattr(story_repo, "get_by_id")
    
    if is_legacy:
        db = story_repo
        story_id = args[1] if len(args) >= 2 else kwargs.get("story_id")
        force_rerun = args[2] if len(args) >= 3 else kwargs.get("force_rerun", False)
        
        from app.repositories.sqlite import SQLStoryRepository, SQLResearchRepository
        story_repo = SQLStoryRepository(db)
        research_repo = SQLResearchRepository(db)
    else:
        research_repo = args[1] if len(args) >= 2 else kwargs.get("research_repo")
        story_id = args[2] if len(args) >= 3 else kwargs.get("story_id")
        force_rerun = args[3] if len(args) >= 4 else kwargs.get("force_rerun", False)

    story = story_repo.get_by_id(story_id)
    if not story:
        logger.error(f"Story #{story_id} not found in database. Aborting research.")
        return "FAILED"

    # 1. Retrieve or create Research Report
    report = research_repo.get_report_by_story_id(story_id)
    if not report:
        report = research_repo.create_report(story_id, status="QUEUED")
        
    # Enforce idempotency: skip if already completed unless forced
    if report.status in {"COMPLETED", "NEEDS_REVIEW"} and not force_rerun:
        logger.info(f"Story #{story_id} research already completed (Status: {report.status}). Skipping.")
        return report.status

    report.status = "RESEARCHING"
    research_repo.save_report(report)

    try:
        # 2. Source Discovery
        discovered_sources = discover_sources(story)
        logger.info(f"Discovered {len(discovered_sources)} source(s) for Story #{story_id}")

        # 3. Fetch, Extract, and Cache Sources
        saved_sources = []
        for src in discovered_sources:
            # Check repository cache
            cached_src = research_repo.get_source_by_url(report.id, src.url)
            
            if cached_src and cached_src.extraction_status == "COMPLETED" and not force_rerun:
                logger.debug(f"Source URL cache hit: {src.url}")
                saved_sources.append(cached_src)
                continue
                
            # Extract content if not cached or forced
            extracted_text = extract_article_content(src.url)
            
            if cached_src:
                domain_source = cached_src
            else:
                domain_source = ResearchSourceData(
                    report_id=report.id,
                    source_name=src.source_name,
                    title=src.title,
                    url=src.url,
                    source_type=src.source_type,
                    priority=src.priority
                )

            if extracted_text:
                domain_source.raw_content = extracted_text
                domain_source.extraction_status = "COMPLETED"
                domain_source.content_hash = hashlib.md5(extracted_text.encode('utf-8')).hexdigest()
                domain_source.last_fetched = datetime.utcnow()
            else:
                domain_source.extraction_status = "FAILED"
                
            saved_source = research_repo.save_source(domain_source)
            saved_sources.append(saved_source)

        # 4. Clear facts and conflicts before extracting new ones
        research_repo.clear_report_facts_and_conflicts(report.id)

        # 5. Fact Extraction
        extracted_facts = []
        for db_source in saved_sources:
            if db_source.extraction_status != "COMPLETED" or not db_source.raw_content:
                continue
                
            raw_facts = extract_facts_from_text(db_source.raw_content, db_source.id)
            for f in raw_facts:
                domain_fact = ResearchFactData(
                    report_id=report.id,
                    fact_type=f.fact_type,
                    original_value=f.original_value,
                    normalized_value=f.normalized_value,
                    currency=f.currency,
                    unit=f.unit,
                    source_id=f.source_id,
                    confidence=int(f.confidence * 100),
                    context=f.context
                )
                saved_fact = research_repo.save_fact(domain_fact)
                extracted_facts.append(saved_fact)

        # 6. Map to core structures for validation engine
        sources_map_core = {s.id: s for s in saved_sources}

        # 7. Cross-Source Verification & Conflict Detection
        verified_facts, conflicts = verify_facts(extracted_facts, sources_map_core)

        # 8. Save detected conflicts
        saved_conflicts = []
        for c in conflicts:
            domain_conflict = ResearchConflictData(
                report_id=report.id,
                conflict_type=c.conflict_type,
                fact_type=c.fact_type,
                source_a=c.source_a,
                value_a=c.value_a,
                source_b=c.source_b,
                value_b=c.value_b,
                severity=c.severity,
                status=c.status
            )
            saved_conflict = research_repo.save_conflict(domain_conflict)
            saved_conflicts.append(saved_conflict)

        # 9. Scorer & Report String builder
        confidence = calculate_research_confidence(
            list(sources_map_core.values()), 
            verified_facts, 
            conflicts
        )

        # Re-fetch fresh report domain model to pass to report compiler
        report = research_repo.get_report_by_id(report.id)
        report_text = build_research_report(
            story,
            list(sources_map_core.values()),
            verified_facts,
            conflicts,
            confidence
        )

        # 10. Update report details & status
        report.what_happened = report_text
        report.why_it_matters = generate_why_it_matters(story.event_type or "OTHER", story.company)
        report.confidence_score = confidence
        
        # If there are unresolved HIGH severity conflicts, status is NEEDS_REVIEW
        has_high_conflict = any(c.severity == "HIGH" and c.status == "OPEN" for c in saved_conflicts)
        if has_high_conflict:
            report.status = "NEEDS_REVIEW"
        else:
            report.status = "COMPLETED"

        research_repo.save_report(report)
        logger.info(f"Research pipeline successfully completed for Story #{story_id} (Status: {report.status}, Confidence: {confidence})")
        return report.status

    except Exception as e:
        logger.error(f"Error executing research pipeline for Story #{story_id}: {e}", exc_info=True)
        report.status = "FAILED"
        research_repo.save_report(report)
        return "FAILED"


def process_research_queue(*args, **kwargs) -> int:
    """
    Stateless processing job loop that queries the repository queue for research-eligible stories.
    Supports signature overloads:
      1. process_research_queue(db, min_importance=70, min_postability=75, concurrency=1)
      2. process_research_queue(story_repo, research_repo, min_importance=70, min_postability=75, concurrency=1)
    """
    story_repo = args[0] if len(args) >= 1 else kwargs.get("story_repo")
    
    # Detect legacy database Session vs Repository interface
    is_legacy = story_repo is not None and not hasattr(story_repo, "get_research_eligible_queue")
    
    if is_legacy:
        db = story_repo
        min_importance = args[1] if len(args) >= 2 else kwargs.get("min_importance", 70)
        min_postability = args[2] if len(args) >= 3 else kwargs.get("min_postability", 75)
        concurrency = args[3] if len(args) >= 4 else kwargs.get("concurrency", 1)
        
        from app.repositories.sqlite import SQLStoryRepository, SQLResearchRepository
        story_repo = SQLStoryRepository(db)
        research_repo = SQLResearchRepository(db)
    else:
        research_repo = args[1] if len(args) >= 2 else kwargs.get("research_repo")
        min_importance = args[2] if len(args) >= 3 else kwargs.get("min_importance", 70)
        min_postability = args[3] if len(args) >= 4 else kwargs.get("min_postability", 75)
        concurrency = args[4] if len(args) >= 5 else kwargs.get("concurrency", 1)

    eligible_stories = story_repo.get_research_eligible_queue(
        min_importance=min_importance,
        min_postability=min_postability,
        limit=concurrency
    )

    logger.info(f"Found {len(eligible_stories)} eligible stories in the queue.")
    
    processed_count = 0
    for story in eligible_stories:
        logger.info(f"Processing research queue item: '{story.title}' (ID: {story.id})")
        
        # Run research, catching exceptions to prevent queue blockage
        try:
            status = research_story(story_repo, research_repo, story.id)
            if status != "FAILED":
                processed_count += 1
        except Exception as e:
            logger.error(f"Failed to process research item {story.id} from queue: {e}")
            
    return processed_count
