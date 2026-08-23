import logging
from app.repositories.interfaces import StoryRepository, ResearchRepository
from app.research.orchestrator import process_research_queue

logger = logging.getLogger(__name__)

def run_research_job(
    story_repo: StoryRepository,
    research_repo: ResearchRepository,
    min_importance: int = 70,
    min_postability: int = 75,
    concurrency: int = 1
) -> int:
    """
    Triggers batch research queue processing.
    Operates strictly via repository interfaces.
    """
    logger.info("Executing scheduled research job...")
    try:
        processed_count = process_research_queue(
            story_repo=story_repo,
            research_repo=research_repo,
            min_importance=min_importance,
            min_postability=min_postability,
            concurrency=concurrency
        )
        return processed_count
    except Exception as e:
        logger.error(f"Error during scheduled research job execution: {e}")
        return 0
