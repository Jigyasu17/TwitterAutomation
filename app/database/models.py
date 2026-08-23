import json
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Story(Base):
    __tablename__ = "stories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    article_url = Column(String, unique=True, nullable=False)
    published_at = Column(DateTime, nullable=False)
    collected_at = Column(DateTime, default=datetime.utcnow)
    category = Column(String, nullable=False)
    company = Column(String, nullable=True)
    country = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    raw_content = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    content_hash = Column(String, unique=True, nullable=False)
    
    # Intelligence scores and event grouping
    event_type = Column(String, nullable=True)
    secondary_tags = Column(Text, nullable=True)  # Comma-separated list
    entities = Column(Text, nullable=True)         # JSON string (Companies, People, Sectors, Countries)
    importance_score = Column(Integer, default=0)
    postability_score = Column(Integer, default=0)
    confidence_score = Column(Integer, default=0)
    final_score = Column(Integer, default=0)
    scoring_breakdown = Column(Text, nullable=True) # JSON string
    
    status = Column(String, default="NEW")  # NEW, FILTERED, READY_FOR_REVIEW, APPROVED, PUBLISHED, REJECTED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sources = relationship("StorySource", back_populates="story", cascade="all, delete-orphan")
    drafts = relationship("Draft", back_populates="story", cascade="all, delete-orphan")
    published_posts = relationship("PublishedPost", back_populates="story", cascade="all, delete-orphan")
    research_report = relationship("ResearchReport", back_populates="story", uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        try:
            parsed_entities = json.loads(self.entities) if self.entities else {}
        except Exception:
            parsed_entities = {}

        try:
            parsed_breakdown = json.loads(self.scoring_breakdown) if self.scoring_breakdown else {}
        except Exception:
            parsed_breakdown = {}

        return {
            "id": self.id,
            "title": self.title,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "article_url": self.article_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "category": self.category,
            "company": self.company,
            "country": self.country,
            "summary": self.summary,
            "image_url": self.image_url,
            "event_type": self.event_type,
            "secondary_tags": [t.strip() for t in self.secondary_tags.split(",") if t.strip()] if self.secondary_tags else [],
            "entities": parsed_entities,
            "importance_score": self.importance_score,
            "postability_score": self.postability_score,
            "confidence_score": self.confidence_score,
            "final_score": self.final_score,
            "scoring_breakdown": parsed_breakdown,
            "status": self.status,
            "sources": [source.to_dict() for source in self.sources],
            "research_report": self.research_report.to_dict() if self.research_report else None
        }

class StorySource(Base):
    __tablename__ = "story_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    source_name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    published_at = Column(DateTime, nullable=False)
    title = Column(String, nullable=False)

    # Relationship
    story = relationship("Story", back_populates="sources")

    def to_dict(self):
        return {
            "id": self.id,
            "story_id": self.story_id,
            "source_name": self.source_name,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "title": self.title
        }

class ResearchReport(Base):
    __tablename__ = "research_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), unique=True, nullable=False)
    status = Column(String, default="NOT_RESEARCHED") # NOT_RESEARCHED, QUEUED, RESEARCHING, COMPLETED, NEEDS_REVIEW, FAILED
    what_happened = Column(Text, nullable=True)
    why_it_matters = Column(Text, nullable=True)
    confidence_score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    story = relationship("Story", back_populates="research_report")
    sources = relationship("ResearchSource", back_populates="report", cascade="all, delete-orphan")
    facts = relationship("ResearchFact", back_populates="report", cascade="all, delete-orphan")
    conflicts = relationship("ResearchConflict", back_populates="report", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "story_id": self.story_id,
            "status": self.status,
            "what_happened": self.what_happened,
            "why_it_matters": self.why_it_matters,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sources": [s.to_dict() for s in self.sources],
            "facts": [f.to_dict() for f in self.facts],
            "conflicts": [c.to_dict() for c in self.conflicts]
        }

class ResearchSource(Base):
    __tablename__ = "research_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("research_reports.id", ondelete="CASCADE"), nullable=False)
    source_name = Column(String, nullable=False)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    canonical_url = Column(String, nullable=True)
    published_date = Column(DateTime, nullable=True)
    discovered_date = Column(DateTime, default=datetime.utcnow)
    source_type = Column(String, default="rss") # rss, google_news, web
    priority = Column(Integer, default=3)
    extraction_status = Column(String, default="NOT_EXTRACTED") # NOT_EXTRACTED, COMPLETED, FAILED
    content_hash = Column(String, nullable=True)
    raw_content = Column(Text, nullable=True)
    last_fetched = Column(DateTime, nullable=True)

    # Relationships
    report = relationship("ResearchReport", back_populates="sources")
    facts = relationship("ResearchFact", back_populates="source", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "report_id": self.report_id,
            "source_name": self.source_name,
            "title": self.title,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "discovered_date": self.discovered_date.isoformat() if self.discovered_date else None,
            "source_type": self.source_type,
            "priority": self.priority,
            "extraction_status": self.extraction_status,
            "content_hash": self.content_hash,
            "last_fetched": self.last_fetched.isoformat() if self.last_fetched else None
        }

class ResearchFact(Base):
    __tablename__ = "research_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("research_reports.id", ondelete="CASCADE"), nullable=False)
    fact_type = Column(String, nullable=False)
    original_value = Column(String, nullable=False)
    normalized_value = Column(Text, nullable=False) # JSON-stringified representation
    currency = Column(String, nullable=True)
    unit = Column(String, nullable=False, default="absolute")
    source_id = Column(Integer, ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=True)
    confidence = Column(Integer, default=0)
    context = Column(Text, nullable=True)

    # Relationships
    report = relationship("ResearchReport", back_populates="facts")
    source = relationship("ResearchSource", back_populates="facts")

    def to_dict(self):
        try:
            parsed_val = json.loads(self.normalized_value)
        except Exception:
            parsed_val = self.normalized_value

        return {
            "id": self.id,
            "report_id": self.report_id,
            "fact_type": self.fact_type,
            "original_value": self.original_value,
            "normalized_value": parsed_val,
            "currency": self.currency,
            "unit": self.unit,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "context": self.context
        }

class ResearchConflict(Base):
    __tablename__ = "research_conflicts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("research_reports.id", ondelete="CASCADE"), nullable=False)
    conflict_type = Column(String, nullable=False)
    fact_type = Column(String, nullable=False)
    source_a = Column(String, nullable=False)
    value_a = Column(String, nullable=False)
    source_b = Column(String, nullable=False)
    value_b = Column(String, nullable=False)
    severity = Column(String, default="LOW") # LOW, MEDIUM, HIGH
    status = Column(String, default="OPEN") # OPEN, RESOLVED, IGNORED

    # Relationship
    report = relationship("ResearchReport", back_populates="conflicts")

    def to_dict(self):
        return {
            "id": self.id,
            "report_id": self.report_id,
            "conflict_type": self.conflict_type,
            "fact_type": self.fact_type,
            "source_a": self.source_a,
            "value_a": self.value_a,
            "source_b": self.source_b,
            "value_b": self.value_b,
            "severity": self.severity,
            "status": self.status
        }

class Draft(Base):
    __tablename__ = "drafts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    post_text = Column(Text, nullable=False)
    thread_json = Column(Text, nullable=True)  # Stores list of strings representing threads
    image_headline = Column(String, nullable=True)
    image_subheadline = Column(String, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    edited_text = Column(Text, nullable=True)
    status = Column(String, default="NEW")

    # Relationship
    story = relationship("Story", back_populates="drafts")

class PublishedPost(Base):
    __tablename__ = "published_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    post_text = Column(Text, nullable=False)
    published_at = Column(DateTime, default=datetime.utcnow)
    x_url = Column(String, nullable=True)

    # Relationship
    story = relationship("Story", back_populates="published_posts")
