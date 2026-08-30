from typing import Optional
from fastapi import Depends
from sqlalchemy.orm import Session
from app.config import settings
from app.database.database import get_db
from app.repositories.interfaces import StoryRepository, ResearchRepository, DraftRepository
from app.repositories.sqlite.story_repository import SQLStoryRepository
from app.repositories.sqlite.research_repository import SQLResearchRepository
from app.repositories.sqlite.draft_repository import SQLDraftRepository

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

def create_draft_repository(db: Optional[Session] = None) -> DraftRepository:
    """
    Creates and returns a DraftRepository implementation based on configurations.
    If database backend is set to firestore, returns a Firestore draft repository.
    Otherwise, defaults to SQLite.
    """
    if settings.DATABASE_BACKEND == "firestore":
        from app.repositories.firestore.draft_repository import FirestoreDraftRepository
        return FirestoreDraftRepository()

    if db is None:
        from app.database.database import SessionLocal
        db = SessionLocal()

    return SQLDraftRepository(db)


# --- FastAPI Dependency Injectors ---

def get_story_repo(db: Session = Depends(get_db)) -> StoryRepository:
    """FastAPI Depends injector for StoryRepository."""
    return create_story_repository(db)

def get_research_repo(db: Session = Depends(get_db)) -> ResearchRepository:
    """FastAPI Depends injector for ResearchRepository."""
    return create_research_repository(db)

def get_draft_repo(db: Session = Depends(get_db)) -> DraftRepository:
    """FastAPI Depends injector for DraftRepository."""
    return create_draft_repository(db)
