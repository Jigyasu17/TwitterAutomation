import datetime
import logging
from typing import List, Optional
from google.cloud import firestore
from app.domain.models import DraftData, PublishedPostData
from app.repositories.interfaces import DraftRepository
from app.repositories.firestore.client import get_firestore_client
from app.repositories.firestore.story_repository import normalize_timestamp

logger = logging.getLogger(__name__)

# --- Helper Serialization Functions ---

def map_draft_dict_to_domain(doc_id: str, data: dict) -> DraftData:
    return DraftData(
        id=doc_id,
        story_id=data.get("story_id"),
        post_text=data.get("post_text", ""),
        thread_json=data.get("thread_json"),
        image_headline=data.get("image_headline"),
        image_subheadline=data.get("image_subheadline"),
        generated_at=normalize_timestamp(data.get("generated_at")),
        edited_text=data.get("edited_text"),
        status=data.get("status", "NEW")
    )

def map_draft_domain_to_dict(draft: DraftData) -> dict:
    return {
        # Stored as a string, matching the convention in
        # firestore/research_repository.py's create_report(), so equality
        # queries on this field (get_draft_by_story_id) reliably match
        # regardless of whether the caller passed an int or a string.
        "story_id": str(draft.story_id),
        "post_text": draft.post_text,
        "thread_json": draft.thread_json,
        "image_headline": draft.image_headline,
        "image_subheadline": draft.image_subheadline,
        "generated_at": normalize_timestamp(draft.generated_at or datetime.datetime.utcnow()),
        "edited_text": draft.edited_text,
        "status": draft.status
    }

def map_published_post_dict_to_domain(doc_id: str, data: dict) -> PublishedPostData:
    return PublishedPostData(
        id=doc_id,
        story_id=data.get("story_id"),
        post_text=data.get("post_text", ""),
        published_at=normalize_timestamp(data.get("published_at")),
        x_url=data.get("x_url")
    )


# --- DraftRepository Firestore Implementation ---

class FirestoreDraftRepository(DraftRepository):
    def __init__(self, client: Optional[firestore.Client] = None):
        self.client = client or get_firestore_client()
        self.collection_name = "drafts"
        self.published_collection_name = "published_posts"

    def get_draft_by_story_id(self, story_id) -> Optional[DraftData]:
        try:
            query = self.client.collection(self.collection_name).where("story_id", "==", str(story_id)).limit(1)
            docs = query.get()
            if docs:
                return map_draft_dict_to_domain(docs[0].id, docs[0].to_dict())
            return None
        except Exception as e:
            logger.error(f"Firestore error in get_draft_by_story_id: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_draft_by_id(self, draft_id) -> Optional[DraftData]:
        try:
            doc = self.client.collection(self.collection_name).document(str(draft_id)).get()
            if doc.exists:
                return map_draft_dict_to_domain(doc.id, doc.to_dict())
            return None
        except Exception as e:
            logger.error(f"Firestore error in get_draft_by_id: {e}")
            raise RuntimeError(f"Database error: {e}")

    def save_draft(self, draft: DraftData) -> DraftData:
        try:
            col_ref = self.client.collection(self.collection_name)
            if draft.id:
                doc_ref = col_ref.document(str(draft.id))
            else:
                doc_ref = col_ref.document()
                draft.id = doc_ref.id

            doc_data = map_draft_domain_to_dict(draft)
            doc_ref.set(doc_data)
            return map_draft_dict_to_domain(doc_ref.id, doc_data)
        except Exception as e:
            logger.error(f"Firestore error in save_draft: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_drafts(self, status: str = "all", limit: int = 50) -> List[DraftData]:
        try:
            query = self.client.collection(self.collection_name)
            if status != "all":
                query = query.where("status", "==", status)
            query = query.limit(limit)
            docs = query.get()
            return [map_draft_dict_to_domain(d.id, d.to_dict()) for d in docs]
        except Exception as e:
            logger.error(f"Firestore error in get_drafts: {e}")
            raise RuntimeError(f"Database error: {e}")

    def mark_published(self, draft_id, x_url: Optional[str] = None) -> PublishedPostData:
        try:
            draft_ref = self.client.collection(self.collection_name).document(str(draft_id))
            draft_doc = draft_ref.get()
            if not draft_doc.exists:
                raise ValueError(f"Draft #{draft_id} not found")

            draft_data = draft_doc.to_dict()
            final_text = draft_data.get("edited_text") or draft_data.get("post_text")

            post_ref = self.client.collection(self.published_collection_name).document()
            post_dict = {
                "story_id": draft_data.get("story_id"),
                "post_text": final_text,
                "published_at": datetime.datetime.utcnow(),
                "x_url": x_url
            }
            post_ref.set(post_dict)

            draft_data["status"] = "POSTED"
            draft_ref.set(draft_data)
            return map_published_post_dict_to_domain(post_ref.id, post_dict)
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Firestore error in mark_published: {e}")
            raise RuntimeError(f"Database error: {e}")

    def discard_draft(self, draft_id) -> DraftData:
        try:
            draft_ref = self.client.collection(self.collection_name).document(str(draft_id))
            draft_doc = draft_ref.get()
            if not draft_doc.exists:
                raise ValueError(f"Draft #{draft_id} not found")

            draft_data = draft_doc.to_dict()
            draft_data["status"] = "DISCARDED"
            draft_ref.set(draft_data)
            return map_draft_dict_to_domain(draft_ref.id, draft_data)
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Firestore error in discard_draft: {e}")
            raise RuntimeError(f"Database error: {e}")
