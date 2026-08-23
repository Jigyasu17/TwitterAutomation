import logging
from sqlalchemy import desc, or_, and_
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database.models import Story, StorySource, ResearchReport, ResearchSource, ResearchFact, ResearchConflict

logger = logging.getLogger(__name__)

class SQLStoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, story_id: int) -> Optional[Story]:
        """Fetches a Story by its primary key ID."""
        return self.db.query(Story).filter(Story.id == story_id).first()

    def save(self, story: Story) -> Story:
        """Saves or updates a Story instance."""
        self.db.add(story)
        self.db.commit()
        self.db.refresh(story)
        return story

    def get_unprocessed_new(self) -> List[Story]:
        """Fetches all unprocessed stories in status 'NEW'."""
        return self.db.query(Story).filter(Story.status == "NEW").all()

    def get_research_eligible_queue(
        self, 
        min_importance: int, 
        min_postability: int, 
        limit: int = 10
    ) -> List[Story]:
        """
        Queries stories eligible for research:
        - Must not be REJECTED or FILTERED.
        - Must meet the min_importance OR min_postability scores.
        - Must not have a completed or currently researching report.
        Ordered by final score descending.
        """
        # Select stories where research_report is missing or status is NOT_RESEARCHED/QUEUED/FAILED
        unresearched_query = or_(
            Story.research_report == None,
            ~Story.research_report.has(ResearchReport.status.in_(["COMPLETED", "RESEARCHING", "NEEDS_REVIEW"]))
        )
        
        score_query = or_(
            Story.importance_score >= min_importance,
            Story.postability_score >= min_postability
        )
        
        status_query = Story.status.in_(["NEW", "READY_FOR_REVIEW", "APPROVED"])

        return self.db.query(Story).filter(
            and_(status_query, score_query, unresearched_query)
        ).order_by(desc(Story.final_score), desc(Story.published_at)).limit(limit).all()


class SQLResearchRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_report_by_story_id(self, story_id: int) -> Optional[ResearchReport]:
        """Retrieves a research report by its associated story ID."""
        return self.db.query(ResearchReport).filter(ResearchReport.story_id == story_id).first()

    def get_report_by_id(self, report_id: int) -> Optional[ResearchReport]:
        """Retrieves a research report by its primary ID."""
        return self.db.query(ResearchReport).filter(ResearchReport.id == report_id).first()

    def create_report(self, story_id: int, status: str = "NOT_RESEARCHED") -> ResearchReport:
        """Creates and commits a new blank research report linked to a story."""
        report = ResearchReport(story_id=story_id, status=status)
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def save_report(self, report: ResearchReport) -> ResearchReport:
        """Saves or updates a ResearchReport instance."""
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def save_source(self, source: ResearchSource) -> ResearchSource:
        """Saves or updates a ResearchSource instance."""
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def get_source_by_url(self, report_id: int, url: str) -> Optional[ResearchSource]:
        """Checks if a URL has already been fetched for a given report ID (Cache check)."""
        return self.db.query(ResearchSource).filter(
            ResearchSource.report_id == report_id,
            ResearchSource.url == url
        ).first()

    def get_sources_for_report(self, report_id: int) -> List[ResearchSource]:
        """Fetches all research sources belonging to a report."""
        return self.db.query(ResearchSource).filter(ResearchSource.report_id == report_id).all()

    def save_fact(self, fact: ResearchFact) -> ResearchFact:
        """Saves or updates a ResearchFact instance."""
        self.db.add(fact)
        self.db.commit()
        self.db.refresh(fact)
        return fact

    def save_conflict(self, conflict: ResearchConflict) -> ResearchConflict:
        """Saves or updates a ResearchConflict instance."""
        self.db.add(conflict)
        self.db.commit()
        self.db.refresh(conflict)
        return conflict

    def get_unresolved_conflicts(self, report_id: int) -> List[ResearchConflict]:
        """Fetches all open, unresolved conflicts for a report."""
        return self.db.query(ResearchConflict).filter(
            ResearchConflict.report_id == report_id,
            ResearchConflict.status == "OPEN"
        ).all()

    def clear_report_facts_and_conflicts(self, report_id: int):
        """Deletes all facts and conflicts associated with a report to clean state for reruns."""
        self.db.query(ResearchFact).filter(ResearchFact.report_id == report_id).delete()
        self.db.query(ResearchConflict).filter(ResearchConflict.report_id == report_id).delete()
        self.db.commit()
