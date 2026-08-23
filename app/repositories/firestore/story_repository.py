import datetime
import logging
from typing import List, Optional, Dict, Any
from google.cloud import firestore
from app.domain.models import StoryData, StorySourceData, ResearchReportData
from app.repositories.interfaces import StoryRepository
from app.repositories.firestore.client import get_firestore_client

logger = logging.getLogger(__name__)

# --- Helper Serialization Functions ---

def normalize_timestamp(dt) -> Optional[datetime.datetime]:
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            return datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return None
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    if hasattr(dt, "timestamp"):
        return datetime.datetime.fromtimestamp(dt.timestamp(), tz=datetime.timezone.utc)
    return dt

def map_source_dict_to_domain(src_dict: dict, src_id: Optional[str] = None) -> StorySourceData:
    return StorySourceData(
        source_name=src_dict.get("source_name", ""),
        url=src_dict.get("url", ""),
        published_at=normalize_timestamp(src_dict.get("published_at")),
        title=src_dict.get("title", ""),
        story_id=src_dict.get("story_id"),
        id=src_id or src_dict.get("id")
    )

def map_source_domain_to_dict(src: StorySourceData) -> dict:
    return {
        "id": src.id,
        "source_name": src.source_name,
        "url": src.url,
        "published_at": normalize_timestamp(src.published_at),
        "title": src.title,
        "story_id": src.story_id
    }

def map_story_dict_to_domain(doc_id: str, data: dict) -> StoryData:
    sources_data = data.get("sources", [])
    sources = [map_source_dict_to_domain(src) for src in sources_data]
    
    return StoryData(
        id=doc_id,
        title=data.get("title", ""),
        source_name=data.get("source_name", ""),
        source_url=data.get("source_url", ""),
        article_url=data.get("article_url", ""),
        published_at=normalize_timestamp(data.get("published_at")),
        collected_at=normalize_timestamp(data.get("collected_at")),
        category=data.get("category", ""),
        content_hash=data.get("content_hash", ""),
        company=data.get("company"),
        country=data.get("country"),
        summary=data.get("summary"),
        image_url=data.get("image_url"),
        event_type=data.get("event_type"),
        secondary_tags=data.get("secondary_tags", []),
        entities=data.get("entities", {}),
        importance_score=data.get("importance_score", 0),
        postability_score=data.get("postability_score", 0),
        confidence_score=data.get("confidence_score", 0),
        final_score=data.get("final_score", 0),
        scoring_breakdown=data.get("scoring_breakdown", {}),
        status=data.get("status", "NEW"),
        sources=sources,
        created_at=normalize_timestamp(data.get("created_at")),
        updated_at=normalize_timestamp(data.get("updated_at"))
    )

def map_story_domain_to_dict(story: StoryData) -> dict:
    return {
        "title": story.title,
        "source_name": story.source_name,
        "source_url": story.source_url,
        "article_url": story.article_url,
        "published_at": normalize_timestamp(story.published_at),
        "collected_at": normalize_timestamp(story.collected_at or datetime.datetime.utcnow()),
        "category": story.category,
        "content_hash": story.content_hash,
        "company": story.company,
        "country": story.country,
        "summary": story.summary,
        "image_url": story.image_url,
        "event_type": story.event_type,
        "secondary_tags": story.secondary_tags,
        "entities": story.entities,
        "importance_score": story.importance_score,
        "postability_score": story.postability_score,
        "confidence_score": story.confidence_score,
        "final_score": story.final_score,
        "scoring_breakdown": story.scoring_breakdown,
        "status": story.status,
        "sources": [map_source_domain_to_dict(src) for src in story.sources],
        "created_at": normalize_timestamp(story.created_at or datetime.datetime.utcnow()),
        "updated_at": normalize_timestamp(story.updated_at or datetime.datetime.utcnow())
    }


# --- StoryRepository Firestore Implementation ---

class FirestoreStoryRepository(StoryRepository):
    def __init__(self, client: Optional[firestore.Client] = None):
        self.client = client or get_firestore_client()
        self.collection_name = "stories"

    def get_by_id(self, story_id: Any) -> Optional[StoryData]:
        try:
            doc_ref = self.client.collection(self.collection_name).document(str(story_id))
            doc = doc_ref.get()
            if doc.exists:
                story = map_story_dict_to_domain(doc.id, doc.to_dict())
                
                # Retrieve linked research report status for compliance
                reports = self.client.collection("research_reports").where("story_id", "==", doc.id).limit(1).get()
                if reports:
                    from app.repositories.firestore.research_repository import map_report_dict_to_domain
                    story.research_report = map_report_dict_to_domain(reports[0].id, reports[0].to_dict())
                return story
            return None
        except Exception as e:
            logger.error(f"Firestore error in get_by_id: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_by_url(self, url: str) -> Optional[StoryData]:
        try:
            query = self.client.collection(self.collection_name).where("article_url", "==", url).limit(1)
            docs = query.get()
            if docs:
                return map_story_dict_to_domain(docs[0].id, docs[0].to_dict())
            return None
        except Exception as e:
            logger.error(f"Firestore error in get_by_url: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_by_hash(self, content_hash: str) -> Optional[StoryData]:
        try:
            query = self.client.collection(self.collection_name).where("content_hash", "==", content_hash).limit(1)
            docs = query.get()
            if docs:
                return map_story_dict_to_domain(docs[0].id, docs[0].to_dict())
            return None
        except Exception as e:
            logger.error(f"Firestore error in get_by_hash: {e}")
            raise RuntimeError(f"Database error: {e}")

    def save(self, story: StoryData) -> StoryData:
        try:
            col_ref = self.client.collection(self.collection_name)
            if story.id:
                doc_ref = col_ref.document(str(story.id))
            else:
                doc_ref = col_ref.document()
                story.id = doc_ref.id

            # Save subcollection sources as well
            for src in story.sources:
                src.story_id = story.id
                if not src.id:
                    src_ref = doc_ref.collection("sources").document()
                    src.id = src_ref.id
                else:
                    src_ref = doc_ref.collection("sources").document(str(src.id))
                src_ref.set(map_source_domain_to_dict(src))

            # Set parent document values
            doc_data = map_story_domain_to_dict(story)
            doc_ref.set(doc_data)
            
            return map_story_dict_to_domain(doc_ref.id, doc_data)
        except Exception as e:
            logger.error(f"Firestore error in save: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_unprocessed_new(self) -> List[StoryData]:
        try:
            query = self.client.collection(self.collection_name).where("status", "==", "NEW")
            docs = query.get()
            return [map_story_dict_to_domain(d.id, d.to_dict()) for d in docs]
        except Exception as e:
            logger.error(f"Firestore error in get_unprocessed_new: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_research_eligible_queue(
        self, 
        min_importance: int, 
        min_postability: int, 
        limit: int = 10
    ) -> List[StoryData]:
        try:
            # Query candidate stories filtered by active statuses and minimum composite final score
            query = self.client.collection(self.collection_name)\
                .where("status", "in", ["NEW", "READY_FOR_REVIEW", "APPROVED"])\
                .where("final_score", ">=", 40)\
                .order_by("final_score", direction=firestore.Query.DESCENDING)\
                .limit(limit * 3)
            
            docs = query.get()
            candidates = [map_story_dict_to_domain(d.id, d.to_dict()) for d in docs]
            
            eligible = []
            for story in candidates:
                # 1. Inequality validation
                if story.importance_score < min_importance and story.postability_score < min_postability:
                    continue
                
                # 2. Check if a report exists with COMPLETED, RESEARCHING, or NEEDS_REVIEW status
                reports = self.client.collection("research_reports").where("story_id", "==", story.id).limit(1).get()
                if reports:
                    rep_status = reports[0].to_dict().get("status")
                    if rep_status in ["COMPLETED", "RESEARCHING", "NEEDS_REVIEW"]:
                        continue
                
                eligible.append(story)
                if len(eligible) >= limit:
                    break
                    
            return eligible
        except Exception as e:
            logger.error(f"Firestore error in get_research_eligible_queue: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_stories(
        self, 
        status: str = "all", 
        category: Optional[str] = None, 
        priority: str = "all", 
        sort_by: str = "score", 
        limit: int = 50, 
        offset: int = 0
    ) -> List[StoryData]:
        try:
            query = self.client.collection(self.collection_name)
            
            if category:
                query = query.where("category", "==", category)
                
            if status == "all":
                query = query.where("status", "in", ["NEW", "READY_FOR_REVIEW", "APPROVED"])
            elif status != "any" and status:
                query = query.where("status", "==", status)

            if priority == "high":
                query = query.where("final_score", ">=", 75)
            elif priority == "medium":
                query = query.where("final_score", ">=", 40).where("final_score", "<", 75)
            elif priority == "low":
                query = query.where("final_score", "<", 40)

            # Firestore sorting
            if sort_by == "newest":
                query = query.order_by("published_at", direction=firestore.Query.DESCENDING)
            else:
                query = query.order_by("final_score", direction=firestore.Query.DESCENDING)\
                             .order_by("published_at", direction=firestore.Query.DESCENDING)

            # Limit and offset implementation
            query = query.offset(offset).limit(limit)
            docs = query.get()
            
            stories = []
            for d in docs:
                story = map_story_dict_to_domain(d.id, d.to_dict())
                
                # Fetch linked report if any
                reports = self.client.collection("research_reports").where("story_id", "==", d.id).limit(1).get()
                if reports:
                    from app.repositories.firestore.research_repository import map_report_dict_to_domain
                    story.research_report = map_report_dict_to_domain(reports[0].id, reports[0].to_dict())
                stories.append(story)
                
            return stories
        except Exception as e:
            logger.error(f"Firestore error in get_stories: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_stats(self) -> Dict[str, int]:
        try:
            stories_col = self.client.collection(self.collection_name)
            
            # Using native aggregate counts for cost efficiency (1 read charge per 1000 items)
            total_articles_agg = self.client.collection_group("sources").count().get()
            total_articles = total_articles_agg[0][0].value if total_articles_agg else 0
            
            unique_agg = stories_col.where("status", "in", ["NEW", "READY_FOR_REVIEW", "APPROVED"]).count().get()
            unique_events = unique_agg[0][0].value if unique_agg else 0
            
            high_agg = stories_col.where("status", "in", ["NEW", "READY_FOR_REVIEW", "APPROVED"])\
                                  .where("final_score", ">=", 75).count().get()
            high_priority = high_agg[0][0].value if high_agg else 0
            
            medium_agg = stories_col.where("status", "in", ["NEW", "READY_FOR_REVIEW", "APPROVED"])\
                                    .where("final_score", ">=", 40)\
                                    .where("final_score", "<", 75).count().get()
            medium_priority = medium_agg[0][0].value if medium_agg else 0
            
            rejected_agg = stories_col.where("status", "==", "REJECTED").count().get()
            rejected = rejected_agg[0][0].value if rejected_agg else 0
            
            return {
                "total_articles": total_articles,
                "unique_events": unique_events,
                "high_priority": high_priority,
                "medium_priority": medium_priority,
                "rejected": rejected
            }
        except Exception as e:
            logger.error(f"Firestore error in get_stats: {e}")
            return {
                "total_articles": 0,
                "unique_events": 0,
                "high_priority": 0,
                "medium_priority": 0,
                "rejected": 0
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
