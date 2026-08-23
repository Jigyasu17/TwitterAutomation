from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.repositories.sqlite import SQLStoryRepository

router = APIRouter(prefix="/api/stats", tags=["stats"])

@router.get("")
def get_stats(db: Session = Depends(get_db)):
    """Computes daily counter stats for the dashboard header."""
    try:
        repo = SQLStoryRepository(db)
        return repo.get_stats()
    except Exception as e:
        # Fallback to zeros in case of error
        return {
            "total_articles": 0,
            "unique_events": 0,
            "high_priority": 0,
            "medium_priority": 0,
            "rejected": 0
        }
