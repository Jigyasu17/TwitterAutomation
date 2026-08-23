import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import desc, or_, and_, func
from sqlalchemy.orm import Session
from app.database.models import Story, StorySource
from app.domain.models import StoryData, StorySourceData, ResearchReportData
from app.repositories.interfaces import StoryRepository
from app.processing.normalize import normalize_url
from app.processing.classifier import extract_entities, SOURCE_PRIORITIES, clean_and_lower

logger = logging.getLogger(__name__)

# --- Model Mapper Helper Functions ---

def map_source_orm_to_domain(src_orm: StorySource) -> StorySourceData:
    return StorySourceData(
        source_name=src_orm.source_name,
        url=src_orm.url,
        published_at=src_orm.published_at,
        title=src_orm.title,
        story_id=src_orm.story_id,
        id=src_orm.id
    )

def map_story_orm_to_domain(story_orm: Story, identity_map: Optional[Dict[int, StoryData]] = None) -> StoryData:
    if identity_map is not None and story_orm.id is not None and story_orm.id in identity_map:
        # Retrieve and update existing domain object in-place to preserve object identity
        story_data = identity_map[story_orm.id]
        story_data.title = story_orm.title
        story_data.source_name = story_orm.source_name
        story_data.source_url = story_orm.source_url
        story_data.article_url = story_orm.article_url
        story_data.published_at = story_orm.published_at
        story_data.collected_at = story_orm.collected_at
        story_data.category = story_orm.category
        story_data.content_hash = story_orm.content_hash
        story_data.company = story_orm.company
        story_data.country = story_orm.country
        story_data.summary = story_orm.summary
        story_data.image_url = story_orm.image_url
        story_data.event_type = story_orm.event_type
        story_data.secondary_tags = [t.strip() for t in story_orm.secondary_tags.split(",") if t.strip()] if story_orm.secondary_tags else []
        try:
            story_data.entities = json.loads(story_orm.entities) if story_orm.entities else {}
        except Exception:
            story_data.entities = {}
        story_data.importance_score = story_orm.importance_score
        story_data.postability_score = story_orm.postability_score
        story_data.confidence_score = story_orm.confidence_score
        story_data.final_score = story_orm.final_score
        try:
            story_data.scoring_breakdown = json.loads(story_orm.scoring_breakdown) if story_orm.scoring_breakdown else {}
        except Exception:
            story_data.scoring_breakdown = {}
        story_data.status = story_orm.status
        story_data.sources = [map_source_orm_to_domain(src) for src in story_orm.sources]
        
        report_data = None
        if story_orm.research_report:
            from app.repositories.sqlite.research_repository import map_report_orm_to_domain
            report_data = map_report_orm_to_domain(story_orm.research_report)
        story_data.research_report = report_data
        
        return story_data

    # Convert lazy loads mapping for research_report
    report_data = None
    if story_orm.research_report:
        r = story_orm.research_report
        # Convert lazy facts/sources/conflicts
        from app.repositories.sqlite.research_repository import map_report_orm_to_domain
        report_data = map_report_orm_to_domain(r)

    try:
        parsed_entities = json.loads(story_orm.entities) if story_orm.entities else {}
    except Exception:
        parsed_entities = {}

    try:
        parsed_breakdown = json.loads(story_orm.scoring_breakdown) if story_orm.scoring_breakdown else {}
    except Exception:
        parsed_breakdown = {}

    story_data = StoryData(
        id=story_orm.id,
        title=story_orm.title,
        source_name=story_orm.source_name,
        source_url=story_orm.source_url,
        article_url=story_orm.article_url,
        published_at=story_orm.published_at,
        collected_at=story_orm.collected_at,
        category=story_orm.category,
        content_hash=story_orm.content_hash,
        company=story_orm.company,
        country=story_orm.country,
        summary=story_orm.summary,
        image_url=story_orm.image_url,
        event_type=story_orm.event_type,
        secondary_tags=[t.strip() for t in story_orm.secondary_tags.split(",") if t.strip()] if story_orm.secondary_tags else [],
        entities=parsed_entities,
        importance_score=story_orm.importance_score,
        postability_score=story_orm.postability_score,
        confidence_score=story_orm.confidence_score,
        final_score=story_orm.final_score,
        scoring_breakdown=parsed_breakdown,
        status=story_orm.status,
        sources=[map_source_orm_to_domain(src) for src in story_orm.sources],
        research_report=report_data,
        created_at=story_orm.created_at,
        updated_at=story_orm.updated_at
    )
    
    if identity_map is not None and story_orm.id is not None:
        identity_map[story_orm.id] = story_data
        
    return story_data

def update_story_orm_from_domain(story_orm: Story, story_data: StoryData) -> None:
    story_orm.title = story_data.title
    story_orm.source_name = story_data.source_name
    story_orm.source_url = story_data.source_url
    story_orm.article_url = story_data.article_url
    story_orm.published_at = story_data.published_at
    story_orm.category = story_data.category
    story_orm.company = story_data.company
    story_orm.country = story_data.country
    story_orm.summary = story_data.summary
    story_orm.image_url = story_data.image_url
    story_orm.event_type = story_data.event_type
    story_orm.secondary_tags = ",".join(story_data.secondary_tags)
    story_orm.entities = json.dumps(story_data.entities)
    story_orm.importance_score = story_data.importance_score
    story_orm.postability_score = story_data.postability_score
    story_orm.confidence_score = story_data.confidence_score
    story_orm.final_score = story_data.final_score
    story_orm.scoring_breakdown = json.dumps(story_data.scoring_breakdown)
    story_orm.status = story_data.status
    story_orm.content_hash = story_data.content_hash

# --- Repository Implementation ---

class SQLStoryRepository(StoryRepository):
    def __init__(self, db: Session):
        self.db = db
        # Bind the identity map to the SQL session instance so it persists across repository rebuilds
        if not hasattr(db, "_repo_identity_map"):
            db._repo_identity_map = {}
        self._identity_map = db._repo_identity_map

    def get_by_id(self, story_id: int) -> Optional[StoryData]:
        story_orm = self.db.query(Story).filter(Story.id == story_id).first()
        return map_story_orm_to_domain(story_orm, self._identity_map) if story_orm else None

    def get_by_url(self, url: str) -> Optional[StoryData]:
        story_orm = self.db.query(Story).filter(Story.article_url == url).first()
        return map_story_orm_to_domain(story_orm, self._identity_map) if story_orm else None

    def get_by_hash(self, content_hash: str) -> Optional[StoryData]:
        story_orm = self.db.query(Story).filter(Story.content_hash == content_hash).first()
        return map_story_orm_to_domain(story_orm, self._identity_map) if story_orm else None

    def save(self, story_data: StoryData) -> StoryData:
        if story_data.id:
            story_orm = self.db.query(Story).filter(Story.id == story_data.id).first()
            if story_orm:
                update_story_orm_from_domain(story_orm, story_data)
                story_orm.updated_at = datetime.utcnow()
        else:
            story_orm = Story()
            update_story_orm_from_domain(story_orm, story_data)
            story_orm.created_at = datetime.utcnow()
            story_orm.updated_at = datetime.utcnow()
            self.db.add(story_orm)
            
        self.db.commit()
        self.db.refresh(story_orm)
        
        # Save sources ORM mapping
        for src in story_data.sources:
            if not src.id:
                src_orm = StorySource(
                    story_id=story_orm.id,
                    source_name=src.source_name,
                    url=src.url,
                    published_at=src.published_at,
                    title=src.title
                )
                self.db.add(src_orm)
        self.db.commit()
        self.db.refresh(story_orm)
        
        # Register in identity map
        story_data.id = story_orm.id
        self._identity_map[story_orm.id] = story_data
        
        return map_story_orm_to_domain(story_orm, self._identity_map)

    def get_unprocessed_new(self) -> List[StoryData]:
        stories_orm = self.db.query(Story).filter(Story.status == "NEW").all()
        return [map_story_orm_to_domain(s, self._identity_map) for s in stories_orm]

    def get_research_eligible_queue(
        self, 
        min_importance: int, 
        min_postability: int, 
        limit: int = 10
    ) -> List[StoryData]:
        from app.database.models import ResearchReport
        unresearched_query = or_(
            Story.research_report == None,
            ~Story.research_report.has(ResearchReport.status.in_(["COMPLETED", "RESEARCHING", "NEEDS_REVIEW"]))
        )
        score_query = or_(
            Story.importance_score >= min_importance,
            Story.postability_score >= min_postability
        )
        status_query = Story.status.in_(["NEW", "READY_FOR_REVIEW", "APPROVED"])

        stories_orm = self.db.query(Story).filter(
            and_(status_query, score_query, unresearched_query)
        ).order_by(desc(Story.final_score), desc(Story.published_at)).limit(limit).all()
        
        return [map_story_orm_to_domain(s, self._identity_map) for s in stories_orm]

    def get_stories(
        self, 
        status: str = "all", 
        category: Optional[str] = None, 
        priority: str = "all", 
        sort_by: str = "score", 
        limit: int = 50, 
        offset: int = 0
    ) -> List[StoryData]:
        # Count sources subquery to support sorting
        source_count_sub = self.db.query(
            StorySource.story_id,
            func.count(StorySource.id).label("source_count")
        ).group_by(StorySource.story_id).subquery()

        query = self.db.query(Story).outerjoin(source_count_sub, Story.id == source_count_sub.c.story_id)

        if category:
            query = query.filter(Story.category == category)

        if status == "all":
            query = query.filter(Story.status != "REJECTED").filter(Story.status != "FILTERED")
        elif status != "any" and status:
            query = query.filter(Story.status == status)

        if priority == "high":
            query = query.filter(Story.final_score >= 75)
        elif priority == "medium":
            query = query.filter(Story.final_score >= 40).filter(Story.final_score < 75)
        elif priority == "low":
            query = query.filter(Story.final_score < 40)

        if sort_by == "newest":
            query = query.order_by(desc(Story.published_at))
        elif sort_by == "sources":
            query = query.order_by(desc(func.coalesce(source_count_sub.c.source_count, 1)), desc(Story.published_at))
        else:
            query = query.order_by(desc(Story.final_score), desc(Story.published_at))

        stories_orm = query.offset(offset).limit(limit).all()
        return [map_story_orm_to_domain(s, self._identity_map) for s in stories_orm]

    def get_stats(self) -> Dict[str, int]:
        total_articles = self.db.query(StorySource).count()
        unique_events = self.db.query(Story).filter(Story.status != "REJECTED").count()
        high_priority = self.db.query(Story).filter(
            and_(Story.status != "REJECTED", Story.status != "FILTERED", Story.final_score >= 75)
        ).count()
        medium_priority = self.db.query(Story).filter(
            and_(Story.status != "REJECTED", Story.status != "FILTERED", Story.final_score >= 40, Story.final_score < 75)
        ).count()
        rejected = self.db.query(Story).filter(Story.status == "REJECTED").count()

        return {
            "total_articles": total_articles,
            "unique_events": unique_events,
            "high_priority": high_priority,
            "medium_priority": medium_priority,
            "rejected": rejected
        }

    def find_duplicate_story(
        self, 
        article_url: str, 
        title: str, 
        similarity_threshold: float = 0.8, 
        lookback_days: int = 7
    ) -> Optional[StoryData]:
        from app.processing.deduplication import find_duplicate_story
        return find_duplicate_story(self, article_url, title, similarity_threshold=similarity_threshold, lookback_days=lookback_days)

    def add_or_merge_story(
        self, 
        story_data: dict, 
        similarity_threshold: float = 0.8
    ) -> StoryData:
        from app.processing.deduplication import add_or_merge_story
        return add_or_merge_story(self, story_data, similarity_threshold=similarity_threshold)
