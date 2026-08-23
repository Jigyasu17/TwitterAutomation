from typing import Optional
from fastapi import Depends
from sqlalchemy.orm import Session
from app.config import settings
from app.database.database import get_db
from app.repositories.interfaces import StoryRepository, ResearchRepository
from app.repositories.sqlite.story_repository import SQLStoryRepository
from app.repositories.sqlite.research_repository import SQLResearchRepository

def create_story_repository(db: Optional[Session] = None) -> StoryRepository:
    """
    Creates and returns a StoryRepository implementation based on configurations.
    If database backend is set to firestore, returns a Firestore story repository.
    Otherwise, defaults to SQLite.
    """
    if settings.DATABASE_BACKEND == "firestore":
        from app.repositories.firestore.story_repository import FirestoreStoryRepository
        return FirestoreStoryRepository()
        
    if db is None:
        from app.database.database import SessionLocal
        db = SessionLocal()
        
    return SQLStoryRepository(db)

def create_research_repository(db: Optional[Session] = None) -> ResearchRepository:
    """
    Creates and returns a ResearchRepository implementation based on configurations.
    If database backend is set to firestore, returns a Firestore research repository.
    Otherwise, defaults to SQLite.
    """
    if settings.DATABASE_BACKEND == "firestore":
        from app.repositories.firestore.research_repository import FirestoreResearchRepository
        return FirestoreResearchRepository()
        
    if db is None:
        from app.database.database import SessionLocal
        db = SessionLocal()
        
    return SQLResearchRepository(db)


# --- FastAPI Dependency Injectors ---

def get_story_repo(db: Session = Depends(get_db)) -> StoryRepository:
    """FastAPI Depends injector for StoryRepository."""
    return create_story_repository(db)

def get_research_repo(db: Session = Depends(get_db)) -> ResearchRepository:
    """FastAPI Depends injector for ResearchRepository."""
    return create_research_repository(db)
