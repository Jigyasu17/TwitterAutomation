from typing import Protocol, List, Optional, Dict, Any
from app.domain.models import StoryData, ResearchReportData, ResearchSourceData, ResearchFactData, ResearchConflictData

class StoryRepository(Protocol):
    def get_by_id(self, story_id: int) -> Optional[StoryData]:
        """Retrieves a Story by its primary key ID."""
        ...

    def get_by_url(self, url: str) -> Optional[StoryData]:
        """Retrieves a Story by its normalized article URL."""
        ...

    def get_by_hash(self, content_hash: str) -> Optional[StoryData]:
        """Retrieves a Story by its unique content title hash."""
        ...

    def save(self, story: StoryData) -> StoryData:
        """Saves or updates a Story instance, returning the updated StoryData."""
        ...

    def get_unprocessed_new(self) -> List[StoryData]:
        """Fetches all stories with status 'NEW'."""
        ...

    def get_research_eligible_queue(
        self, 
        min_importance: int, 
        min_postability: int, 
        limit: int = 10
    ) -> List[StoryData]:
        """Queries stories eligible for automated research."""
        ...

    def get_stories(
        self, 
        status: str = "all", 
        category: Optional[str] = None, 
        priority: str = "all", 
        sort_by: str = "score", 
        limit: int = 50, 
        offset: int = 0
    ) -> List[StoryData]:
        """Queries and lists story feeds with advanced sorting, category, and priority filters."""
        ...

    def get_stats(self) -> Dict[str, int]:
        """Computes statistical aggregate counts for dashboard metric counters."""
        ...

    def find_duplicate_story(
        self, 
        article_url: str, 
        title: str, 
        similarity_threshold: float = 0.8, 
        lookback_days: int = 7
    ) -> Optional[StoryData]:
        """Checks for existing stories matching url, title hash, or title string similarity."""
        ...

    def add_or_merge_story(
        self, 
        story_data: dict, 
        similarity_threshold: float = 0.8
    ) -> StoryData:
        """Saves new story entries or updates confirmation sources for duplicate hits."""
        ...


class ResearchRepository(Protocol):
    def get_report_by_story_id(self, story_id: int) -> Optional[ResearchReportData]:
        """Retrieves a research report by its associated story ID."""
        ...

    def get_report_by_id(self, report_id: int) -> Optional[ResearchReportData]:
        """Retrieves a research report by its primary ID."""
        ...

    def create_report(self, story_id: int, status: str = "NOT_RESEARCHED") -> ResearchReportData:
        """Creates a new blank research report linked to a story."""
        ...

    def save_report(self, report: ResearchReportData) -> ResearchReportData:
        """Saves or updates a ResearchReport instance."""
        ...

    def save_source(self, source: ResearchSourceData) -> ResearchSourceData:
        """Saves or updates a ResearchSource instance."""
        ...

    def get_source_by_url(self, report_id: int, url: str) -> Optional[ResearchSourceData]:
        """Checks if a URL has already been fetched for a given report ID (Cache check)."""
        ...

    def get_sources_for_report(self, report_id: int) -> List[ResearchSourceData]:
        """Fetches all research sources belonging to a report."""
        ...

    def save_fact(self, fact: ResearchFactData) -> ResearchFactData:
        """Saves or updates a ResearchFact instance."""
        ...

    def save_conflict(self, conflict: ResearchConflictData) -> ResearchConflictData:
        """Saves or updates a ResearchConflict instance."""
        ...

    def get_unresolved_conflicts(self, report_id: int) -> List[ResearchConflictData]:
        """Fetches all open, unresolved conflicts for a report."""
        ...

    def clear_report_facts_and_conflicts(self, report_id: int) -> None:
        """Deletes all facts and conflicts associated with a report to reset state."""
        ...
