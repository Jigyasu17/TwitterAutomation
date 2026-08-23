import json
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.database.models import ResearchReport, ResearchSource, ResearchFact, ResearchConflict
from app.domain.models import ResearchReportData, ResearchSourceData, ResearchFactData, ResearchConflictData
from app.repositories.interfaces import ResearchRepository

logger = logging.getLogger(__name__)

# --- Model Mapper Helper Functions ---

def map_source_orm_to_domain(s: ResearchSource) -> ResearchSourceData:
    return ResearchSourceData(
        id=s.id,
        report_id=s.report_id,
        source_name=s.source_name,
        title=s.title,
        url=s.url,
        canonical_url=s.canonical_url,
        published_date=s.published_date,
        discovered_date=s.discovered_date,
        source_type=s.source_type,
        priority=s.priority,
        extraction_status=s.extraction_status,
        content_hash=s.content_hash,
        raw_content=s.raw_content,
        last_fetched=s.last_fetched
    )

def update_source_orm_from_domain(orm: ResearchSource, d: ResearchSourceData) -> None:
    orm.report_id = d.report_id
    orm.source_name = d.source_name
    orm.title = d.title
    orm.url = d.url
    orm.canonical_url = d.canonical_url
    orm.published_date = d.published_date
    orm.source_type = d.source_type
    orm.priority = d.priority
    orm.extraction_status = d.extraction_status
    orm.content_hash = d.content_hash
    orm.raw_content = d.raw_content
    orm.last_fetched = d.last_fetched

def map_fact_orm_to_domain(f: ResearchFact) -> ResearchFactData:
    try:
        parsed_val = json.loads(f.normalized_value)
    except Exception:
        parsed_val = f.normalized_value

    return ResearchFactData(
        id=f.id,
        report_id=f.report_id,
        fact_type=f.fact_type,
        original_value=f.original_value,
        normalized_value=parsed_val,
        currency=f.currency,
        unit=f.unit,
        source_id=f.source_id,
        confidence=f.confidence,
        context=f.context
    )

def update_fact_orm_from_domain(orm: ResearchFact, d: ResearchFactData) -> None:
    orm.report_id = d.report_id
    orm.fact_type = d.fact_type
    orm.original_value = d.original_value
    orm.normalized_value = json.dumps(d.normalized_value)
    orm.currency = d.currency
    orm.unit = d.unit
    orm.source_id = d.source_id
    orm.confidence = d.confidence
    orm.context = d.context

def map_conflict_orm_to_domain(c: ResearchConflict) -> ResearchConflictData:
    return ResearchConflictData(
        id=c.id,
        report_id=c.report_id,
        conflict_type=c.conflict_type,
        fact_type=c.fact_type,
        source_a=c.source_a,
        value_a=c.value_a,
        source_b=c.source_b,
        value_b=c.value_b,
        severity=c.severity,
        status=c.status
    )

def update_conflict_orm_from_domain(orm: ResearchConflict, d: ResearchConflictData) -> None:
    orm.report_id = d.report_id
    orm.conflict_type = d.conflict_type
    orm.fact_type = d.fact_type
    orm.source_a = d.source_a
    orm.value_a = d.value_a
    orm.source_b = d.source_b
    orm.value_b = d.value_b
    orm.severity = d.severity
    orm.status = d.status

def map_report_orm_to_domain(report_orm: ResearchReport) -> ResearchReportData:
    return ResearchReportData(
        id=report_orm.id,
        story_id=report_orm.story_id,
        status=report_orm.status,
        what_happened=report_orm.what_happened,
        why_it_matters=report_orm.why_it_matters,
        confidence_score=report_orm.confidence_score,
        created_at=report_orm.created_at,
        updated_at=report_orm.updated_at,
        sources=[map_source_orm_to_domain(s) for s in report_orm.sources],
        facts=[map_fact_orm_to_domain(f) for f in report_orm.facts],
        conflicts=[map_conflict_orm_to_domain(c) for c in report_orm.conflicts]
    )

def update_report_orm_from_domain(orm: ResearchReport, d: ResearchReportData) -> None:
    orm.story_id = d.story_id
    orm.status = d.status
    orm.what_happened = d.what_happened
    orm.why_it_matters = d.why_it_matters
    orm.confidence_score = d.confidence_score

# --- Repository Implementation ---

class SQLResearchRepository(ResearchRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_report_by_story_id(self, story_id: int) -> Optional[ResearchReportData]:
        r = self.db.query(ResearchReport).filter(ResearchReport.story_id == story_id).first()
        return map_report_orm_to_domain(r) if r else None

    def get_report_by_id(self, report_id: int) -> Optional[ResearchReportData]:
        r = self.db.query(ResearchReport).filter(ResearchReport.id == report_id).first()
        return map_report_orm_to_domain(r) if r else None

    def create_report(self, story_id: int, status: str = "NOT_RESEARCHED") -> ResearchReportData:
        report_orm = ResearchReport(story_id=story_id, status=status)
        self.db.add(report_orm)
        self.db.commit()
        self.db.refresh(report_orm)
        return map_report_orm_to_domain(report_orm)

    def save_report(self, report_data: ResearchReportData) -> ResearchReportData:
        if report_data.id:
            report_orm = self.db.query(ResearchReport).filter(ResearchReport.id == report_data.id).first()
            if report_orm:
                update_report_orm_from_domain(report_orm, report_data)
                report_orm.updated_at = datetime.utcnow()
        else:
            report_orm = ResearchReport()
            update_report_orm_from_domain(report_orm, report_data)
            report_orm.created_at = datetime.utcnow()
            report_orm.updated_at = datetime.utcnow()
            self.db.add(report_orm)
            
        self.db.commit()
        self.db.refresh(report_orm)
        
        report_data.id = report_orm.id
        report_data.created_at = report_orm.created_at
        report_data.updated_at = report_orm.updated_at
        return report_data

    def save_source(self, source_data: ResearchSourceData) -> ResearchSourceData:
        if source_data.id:
            orm = self.db.query(ResearchSource).filter(ResearchSource.id == source_data.id).first()
            if orm:
                update_source_orm_from_domain(orm, source_data)
        else:
            orm = ResearchSource()
            update_source_orm_from_domain(orm, source_data)
            self.db.add(orm)
            
        self.db.commit()
        self.db.refresh(orm)
        
        source_data.id = orm.id
        return source_data

    def get_source_by_url(self, report_id: int, url: str) -> Optional[ResearchSourceData]:
        s = self.db.query(ResearchSource).filter(
            ResearchSource.report_id == report_id,
            ResearchSource.url == url
        ).first()
        return map_source_orm_to_domain(s) if s else None

    def get_sources_for_report(self, report_id: int) -> List[ResearchSourceData]:
        sources_orm = self.db.query(ResearchSource).filter(ResearchSource.report_id == report_id).all()
        return [map_source_orm_to_domain(s) for s in sources_orm]

    def save_fact(self, fact_data: ResearchFactData) -> ResearchFactData:
        if fact_data.id:
            orm = self.db.query(ResearchFact).filter(ResearchFact.id == fact_data.id).first()
            if orm:
                update_fact_orm_from_domain(orm, fact_data)
        else:
            orm = ResearchFact()
            update_fact_orm_from_domain(orm, fact_data)
            self.db.add(orm)
            
        self.db.commit()
        self.db.refresh(orm)
        
        fact_data.id = orm.id
        return fact_data

    def save_conflict(self, conflict_data: ResearchConflictData) -> ResearchConflictData:
        if conflict_data.id:
            orm = self.db.query(ResearchConflict).filter(ResearchConflict.id == conflict_data.id).first()
            if orm:
                update_conflict_orm_from_domain(orm, conflict_data)
        else:
            orm = ResearchConflict()
            update_conflict_orm_from_domain(orm, conflict_data)
            self.db.add(orm)
            
        self.db.commit()
        self.db.refresh(orm)
        
        conflict_data.id = orm.id
        return conflict_data

    def get_unresolved_conflicts(self, report_id: int) -> List[ResearchConflictData]:
        conflicts_orm = self.db.query(ResearchConflict).filter(
            ResearchConflict.report_id == report_id,
            ResearchConflict.status == "OPEN"
        ).all()
        return [map_conflict_orm_to_domain(c) for c in conflicts_orm]

    def clear_report_facts_and_conflicts(self, report_id: int) -> None:
        self.db.query(ResearchFact).filter(ResearchFact.report_id == report_id).delete()
        self.db.query(ResearchConflict).filter(ResearchConflict.report_id == report_id).delete()
        self.db.commit()
