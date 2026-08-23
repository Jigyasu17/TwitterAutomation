import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database.database import get_db
from app.repositories.sqlite import SQLStoryRepository, SQLResearchRepository
from app.jobs.collection_job import run_news_collection
from app.jobs.processing_job import run_story_processing
from app.jobs.research_job import run_research_job
from app.research.orchestrator import research_story
from app.processing.classifier import (
    classify_category, 
    identify_event_type, 
    extract_entities, 
    calculate_scores
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stories"])

@router.get("/api/stories")
def get_stories(
    status: str = Query("all", description="Filter stories by status (NEW, REJECTED, etc.). 'all' excludes REJECTED, 'any' includes all."),
    category: str = Query(None, description="Filter by primary category"),
    priority: str = Query("all", description="Filter by priority: high, medium, low, all"),
    sort_by: str = Query("score", description="Sort by: score (default), newest, sources"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Fetches stories with advanced filtering, priority mapping, and source sorting."""
    try:
        story_repo = SQLStoryRepository(db)
        stories = story_repo.get_stories(
            status=status,
            category=category,
            priority=priority,
            sort_by=sort_by,
            limit=limit,
            offset=offset
        )
        return [story.to_dict() for story in stories]
    except Exception as e:
        logger.error(f"Error fetching stories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database query error.")

@router.post("/api/stories/{story_id}/reject")
def reject_story(story_id: int, db: Session = Depends(get_db)):
    """Rejects a story event."""
    story_repo = SQLStoryRepository(db)
    story = story_repo.get_by_id(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story.status = "REJECTED"
    story_repo.save(story)
    logger.info(f"Story {story_id} was manually REJECTED.")
    return {"status": "success", "message": f"Story {story_id} status updated to REJECTED."}

@router.post("/api/stories/{story_id}/approve")
def approve_story(story_id: int, db: Session = Depends(get_db)):
    """Approves a story event."""
    story_repo = SQLStoryRepository(db)
    story = story_repo.get_by_id(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story.status = "APPROVED"
    story_repo.save(story)
    logger.info(f"Story {story_id} was manually APPROVED.")
    return {"status": "success", "message": f"Story {story_id} status updated to APPROVED."}

@router.post("/api/collect")
def collect_news(db: Session = Depends(get_db)):
    """Triggers the collector crawl across feeds (Legacy router)."""
    story_repo = SQLStoryRepository(db)
    result = run_news_collection(story_repo)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result

@router.post("/api/process")
def process_new_stories(db: Session = Depends(get_db)):
    """Triggers the pipeline manual processing run for all NEW unprocessed stories (Legacy router)."""
    try:
        story_repo = SQLStoryRepository(db)
        processed_count = run_story_processing(story_repo)
        return {
            "status": "success",
            "processed_count": processed_count,
            "message": f"Processed {processed_count} new stories."
        }
    except Exception as e:
        logger.error(f"Manual processing trigger failed: {e}")
        raise HTTPException(status_code=500, detail="Processing error occurred.")

@router.post("/api/stories/{story_id}/process")
def process_single_story(story_id: int, db: Session = Depends(get_db)):
    """Manually triggers processing on a single story (re-evaluates classification and scores)."""
    story_repo = SQLStoryRepository(db)
    story = story_repo.get_by_id(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
        
    try:
        category, tags = classify_category(story.title, story.summary or "")
        event_type = identify_event_type(story.title)
        entities = extract_entities(story.title, story.summary or "")
        main_company = entities["Companies"][0] if entities["Companies"] else story.company
        main_country = entities["Countries"][0] if entities["Countries"] else story.country
        
        imp_score, post_score, conf_score, final_score, breakdown = calculate_scores(
            story.title,
            story.summary or "",
            story.source_name,
            len(story.sources)
        )
        
        story.category = category
        story.event_type = event_type
        story.secondary_tags = tags
        story.entities = entities
        story.company = main_company
        story.country = main_country
        story.importance_score = imp_score
        story.postability_score = post_score
        story.confidence_score = conf_score
        story.final_score = final_score
        story.scoring_breakdown = breakdown
        
        story_repo.save(story)
        return {
            "status": "success",
            "story": story.to_dict()
        }
    except Exception as e:
        logger.error(f"Failed to process single story #{story_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process story.")

# --- Research Engine Endpoints ---

@router.post("/api/stories/{story_id}/research")
def trigger_research(story_id: int, db: Session = Depends(get_db)):
    """Triggers the rule-based research pipeline for a single story."""
    try:
        story_repo = SQLStoryRepository(db)
        research_repo = SQLResearchRepository(db)
        status = research_story(story_repo, research_repo, story_id, force_rerun=False)
        return {
            "status": "success",
            "research_status": status,
            "message": f"Story research pipeline finished with status: {status}"
        }
    except Exception as e:
        logger.error(f"Failed to trigger research for story #{story_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to run research.")

@router.post("/api/stories/{story_id}/research-again")
def trigger_research_again(story_id: int, db: Session = Depends(get_db)):
    """Forces the research pipeline to rerun, bypassing cache and clear existing logs."""
    try:
        story_repo = SQLStoryRepository(db)
        research_repo = SQLResearchRepository(db)
        status = research_story(story_repo, research_repo, story_id, force_rerun=True)
        return {
            "status": "success",
            "research_status": status,
            "message": f"Story research pipeline rerun finished with status: {status}"
        }
    except Exception as e:
        logger.error(f"Failed to rerun research for story #{story_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to rerun research.")

@router.get("/api/stories/{story_id}/research")
def get_story_research(story_id: int, db: Session = Depends(get_db)):
    """Fetches the research report and conflict details for a given story ID."""
    research_repo = SQLResearchRepository(db)
    report = research_repo.get_report_by_story_id(story_id)
    if not report:
        raise HTTPException(status_code=404, detail="No research report exists for this story.")
    return report.to_dict()

@router.get("/api/research/queue")
def get_research_queue(
    min_importance: int = Query(70, description="Minimum importance threshold"),
    min_postability: int = Query(75, description="Minimum postability threshold"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Retrieves the list of high-priority stories eligible for research."""
    try:
        story_repo = SQLStoryRepository(db)
        queue = story_repo.get_research_eligible_queue(
            min_importance=min_importance,
            min_postability=min_postability,
            limit=limit
        )
        return [story.to_dict() for story in queue]
    except Exception as e:
        logger.error(f"Error fetching research queue: {e}")
        raise HTTPException(status_code=500, detail="Error fetching queue.")

@router.post("/api/research/process")
def process_research_queue_job(
    min_importance: int = Query(70, description="Min importance score"),
    min_postability: int = Query(75, description="Min postability score"),
    concurrency: int = Query(1, description="Max concurrent processing limit"),
    db: Session = Depends(get_db)
):
    """Triggers batch research queue processing (Legacy router)."""
    try:
        story_repo = SQLStoryRepository(db)
        research_repo = SQLResearchRepository(db)
        processed_count = run_research_job(
            story_repo=story_repo,
            research_repo=research_repo,
            min_importance=min_importance,
            min_postability=min_postability,
            concurrency=concurrency
        )
        return {
            "status": "success",
            "processed_count": processed_count,
            "message": f"Successfully researched {processed_count} story items."
        }
    except Exception as e:
        logger.error(f"Queue processing failed: {e}")
        raise HTTPException(status_code=500, detail="Queue run error.")

# --- Standalone Jobs Endpoints (Cron targets) ---

@router.post("/api/jobs/collect")
def job_collect_endpoint(db: Session = Depends(get_db)):
    """API endpoint to trigger standalone collection cron job."""
    story_repo = SQLStoryRepository(db)
    result = run_news_collection(story_repo)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result

@router.post("/api/jobs/process")
def job_process_endpoint(db: Session = Depends(get_db)):
    """API endpoint to trigger standalone classification and scoring cron job."""
    try:
        story_repo = SQLStoryRepository(db)
        processed_count = run_story_processing(story_repo)
        return {
            "status": "success",
            "processed_count": processed_count
        }
    except Exception as e:
        logger.error(f"Job processing endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Job processing failed.")

@router.post("/api/jobs/research")
def job_research_endpoint(
    min_importance: int = Query(70),
    min_postability: int = Query(75),
    concurrency: int = Query(1),
    db: Session = Depends(get_db)
):
    """API endpoint to trigger standalone research crawler cron job."""
    try:
        story_repo = SQLStoryRepository(db)
        research_repo = SQLResearchRepository(db)
        processed_count = run_research_job(
            story_repo=story_repo,
            research_repo=research_repo,
            min_importance=min_importance,
            min_postability=min_postability,
            concurrency=concurrency
        )
        return {
            "status": "success",
            "processed_count": processed_count
        }
    except Exception as e:
        logger.error(f"Job research endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Job research failed.")
