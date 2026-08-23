from fastapi import APIRouter, Depends
from app.repositories.interfaces import StoryRepository
from app.repositories.factory import get_story_repo

router = APIRouter(prefix="/api/stats", tags=["stats"])

@router.get("")
def get_stats(story_repo: StoryRepository = Depends(get_story_repo)):
    """Computes daily counter stats for the dashboard header."""
    try:
        return story_repo.get_stats()
    except Exception as e:
        # Fallback to zeros in case of error
        return {
            "total_articles": 0,
            "unique_events": 0,
            "high_priority": 0,
            "medium_priority": 0,
            "rejected": 0
        }
