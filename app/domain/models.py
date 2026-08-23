import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

def serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Helper to convert datetime objects to ISO strings."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()

@dataclass
class StorySourceData:
    source_name: str
    url: str
    published_at: datetime
    title: str
    story_id: Optional[int] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["published_at"] = serialize_datetime(self.published_at)
        return d

@dataclass
class ResearchSourceData:
    source_name: str
    title: str
    url: str
    report_id: Optional[int] = None
    canonical_url: Optional[str] = None
    published_date: Optional[datetime] = None
    discovered_date: datetime = field(default_factory=datetime.utcnow)
    source_type: str = "rss"
    priority: int = 3
    extraction_status: str = "NOT_EXTRACTED"
    content_hash: Optional[str] = None
    raw_content: Optional[str] = None
    last_fetched: Optional[datetime] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["published_date"] = serialize_datetime(self.published_date)
        d["discovered_date"] = serialize_datetime(self.discovered_date)
        d["last_fetched"] = serialize_datetime(self.last_fetched)
        return d

@dataclass
class ResearchFactData:
    fact_type: str
    original_value: str
    normalized_value: Any  # Decoded primitive (float, int, range string, dict)
    currency: Optional[str] = None
    unit: str = "absolute"
    confidence: int = 0
    context: Optional[str] = None
    source_id: Optional[int] = None
    report_id: Optional[int] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ResearchConflictData:
    conflict_type: str
    fact_type: str
    source_a: str
    value_a: str
    source_b: str
    value_b: str
    severity: str = "LOW"
    status: str = "OPEN"
    report_id: Optional[int] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ResearchReportData:
    story_id: int
    status: str = "NOT_RESEARCHED"
    what_happened: Optional[str] = None
    why_it_matters: Optional[str] = None
    confidence_score: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    sources: List[ResearchSourceData] = field(default_factory=list)
    facts: List[ResearchFactData] = field(default_factory=list)
    conflicts: List[ResearchConflictData] = field(default_factory=list)
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "story_id": self.story_id,
            "status": self.status,
            "what_happened": self.what_happened,
            "why_it_matters": self.why_it_matters,
            "confidence_score": self.confidence_score,
            "created_at": serialize_datetime(self.created_at),
            "updated_at": serialize_datetime(self.updated_at),
            "sources": [s.to_dict() for s in self.sources],
            "facts": [f.to_dict() for f in self.facts],
            "conflicts": [c.to_dict() for c in self.conflicts]
        }

@dataclass
class StoryData:
    title: str
    source_name: str
    source_url: str
    article_url: str
    published_at: datetime
    category: str
    content_hash: str
    collected_at: datetime = field(default_factory=datetime.utcnow)
    company: Optional[str] = None
    country: Optional[str] = None
    summary: Optional[str] = None
    image_url: Optional[str] = None
    event_type: Optional[str] = None
    secondary_tags: List[str] = field(default_factory=list)
    entities: Dict[str, Any] = field(default_factory=dict)
    importance_score: int = 0
    postability_score: int = 0
    confidence_score: int = 0
    final_score: int = 0
    scoring_breakdown: Dict[str, Any] = field(default_factory=dict)
    status: str = "NEW"
    sources: List[StorySourceData] = field(default_factory=list)
    research_report: Optional[ResearchReportData] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "article_url": self.article_url,
            "published_at": serialize_datetime(self.published_at),
            "collected_at": serialize_datetime(self.collected_at),
            "category": self.category,
            "company": self.company,
            "country": self.country,
            "summary": self.summary,
            "image_url": self.image_url,
            "event_type": self.event_type,
            "secondary_tags": self.secondary_tags,
            "entities": self.entities,
            "importance_score": self.importance_score,
            "postability_score": self.postability_score,
            "confidence_score": self.confidence_score,
            "final_score": self.final_score,
            "scoring_breakdown": self.scoring_breakdown,
            "status": self.status,
            "sources": [s.to_dict() for s in self.sources],
            "research_report": self.research_report.to_dict() if self.research_report else None,
            "created_at": serialize_datetime(self.created_at),
            "updated_at": serialize_datetime(self.updated_at)
        }

@dataclass
class DraftData:
    story_id: int
    post_text: str
    thread_json: Optional[List[str]] = None
    image_headline: Optional[str] = None
    image_subheadline: Optional[str] = None
    generated_at: datetime = field(default_factory=datetime.utcnow)
    edited_text: Optional[str] = None
    status: str = "NEW"
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["generated_at"] = serialize_datetime(self.generated_at)
        return d
