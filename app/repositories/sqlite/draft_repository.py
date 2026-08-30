import json
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.database.models import Draft, PublishedPost
from app.domain.models import DraftData, PublishedPostData
from app.repositories.interfaces import DraftRepository

logger = logging.getLogger(__name__)

# --- Model Mapper Helper Functions ---

def map_draft_orm_to_domain(draft_orm: Draft) -> DraftData:
    try:
        thread = json.loads(draft_orm.thread_json) if draft_orm.thread_json else None
    except Exception:
        thread = None

    return DraftData(
        id=draft_orm.id,
        story_id=draft_orm.story_id,
        post_text=draft_orm.post_text,
        thread_json=thread,
        image_headline=draft_orm.image_headline,
        image_subheadline=draft_orm.image_subheadline,
        generated_at=draft_orm.generated_at,
        edited_text=draft_orm.edited_text,
        status=draft_orm.status
    )

def update_draft_orm_from_domain(draft_orm: Draft, draft_data: DraftData) -> None:
    draft_orm.story_id = draft_data.story_id
    draft_orm.post_text = draft_data.post_text
    draft_orm.thread_json = json.dumps(draft_data.thread_json) if draft_data.thread_json else None
    draft_orm.image_headline = draft_data.image_headline
    draft_orm.image_subheadline = draft_data.image_subheadline
    draft_orm.edited_text = draft_data.edited_text
    draft_orm.status = draft_data.status

def map_published_post_orm_to_domain(post_orm: PublishedPost) -> PublishedPostData:
    return PublishedPostData(
        id=post_orm.id,
        story_id=post_orm.story_id,
        post_text=post_orm.post_text,
        published_at=post_orm.published_at,
        x_url=post_orm.x_url
    )

# --- Repository Implementation ---

class SQLDraftRepository(DraftRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_draft_by_story_id(self, story_id: int) -> Optional[DraftData]:
        draft_orm = self.db.query(Draft).filter(Draft.story_id == story_id).first()
        return map_draft_orm_to_domain(draft_orm) if draft_orm else None

    def get_draft_by_id(self, draft_id: int) -> Optional[DraftData]:
        draft_orm = self.db.query(Draft).filter(Draft.id == draft_id).first()
        return map_draft_orm_to_domain(draft_orm) if draft_orm else None

    def save_draft(self, draft_data: DraftData) -> DraftData:
        if draft_data.id:
            draft_orm = self.db.query(Draft).filter(Draft.id == draft_data.id).first()
            if draft_orm:
                update_draft_orm_from_domain(draft_orm, draft_data)
        else:
            draft_orm = Draft()
            update_draft_orm_from_domain(draft_orm, draft_data)
            draft_orm.generated_at = datetime.utcnow()
            self.db.add(draft_orm)

        self.db.commit()
        self.db.refresh(draft_orm)
        return map_draft_orm_to_domain(draft_orm)

    def get_drafts(self, status: str = "all", limit: int = 50) -> List[DraftData]:
        query = self.db.query(Draft)
        if status != "all":
            query = query.filter(Draft.status == status)
        drafts_orm = query.order_by(Draft.generated_at.desc()).limit(limit).all()
        return [map_draft_orm_to_domain(d) for d in drafts_orm]

    def mark_published(self, draft_id: int, x_url: Optional[str] = None) -> PublishedPostData:
        draft_orm = self.db.query(Draft).filter(Draft.id == draft_id).first()
        if not draft_orm:
            raise ValueError(f"Draft #{draft_id} not found")

        final_text = draft_orm.edited_text or draft_orm.post_text
        post_orm = PublishedPost(
            story_id=draft_orm.story_id,
            post_text=final_text,
            published_at=datetime.utcnow(),
            x_url=x_url
        )
        self.db.add(post_orm)

        draft_orm.status = "POSTED"
        self.db.commit()
        self.db.refresh(post_orm)
        return map_published_post_orm_to_domain(post_orm)

    def discard_draft(self, draft_id: int) -> DraftData:
        draft_orm = self.db.query(Draft).filter(Draft.id == draft_id).first()
        if not draft_orm:
            raise ValueError(f"Draft #{draft_id} not found")

        draft_orm.status = "DISCARDED"
        self.db.commit()
        self.db.refresh(draft_orm)
        return map_draft_orm_to_domain(draft_orm)
