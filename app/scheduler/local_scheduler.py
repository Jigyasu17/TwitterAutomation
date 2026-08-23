import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.repositories.factory import create_story_repository, create_research_repository
from app.jobs.collection_job import run_news_collection
from app.jobs.processing_job import run_story_processing
from app.jobs.research_job import run_research_job
from app.config import settings

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

def collection_job():
    logger.info("Executing local development scheduled collection job...")
    try:
        story_repo = create_story_repository()
        run_news_collection(story_repo)
    except Exception as e:
        logger.error(f"Scheduled collection job failed: {e}")

def processing_job():
    logger.info("Executing local development scheduled story processing job...")
    try:
        story_repo = create_story_repository()
        run_story_processing(story_repo)
    except Exception as e:
        logger.error(f"Scheduled processing job failed: {e}")

def research_job():
    logger.info("Executing local development scheduled research job...")
    try:
        story_repo = create_story_repository()
        research_repo = create_research_repository()
        run_research_job(story_repo, research_repo)
    except Exception as e:
        logger.error(f"Scheduled research job failed: {e}")

def start_scheduler():
    """Configures and starts background scheduler jobs for local environment."""
    if not scheduler.running:
        # Crawl interval
        scheduler.add_job(
            collection_job, 
            "interval", 
            minutes=settings.NEWS_FETCH_INTERVAL_MINUTES, 
            id="collect_job",
            replace_existing=True
        )
        # Processing interval
        scheduler.add_job(
            processing_job, 
            "interval", 
            minutes=settings.NEWS_FETCH_INTERVAL_MINUTES * 2, 
            id="process_job",
            replace_existing=True
        )
        # Research interval
        scheduler.add_job(
            research_job,
            "interval",
            minutes=settings.NEWS_FETCH_INTERVAL_MINUTES * 2,
            id="research_job",
            replace_existing=True
        )
        scheduler.start()
        logger.info("Local background development scheduler started.")

def shutdown_scheduler():
    """Stops background scheduler tasks."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Local background development scheduler stopped.")
