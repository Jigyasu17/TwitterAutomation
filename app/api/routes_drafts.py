import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from app.repositories.interfaces import StoryRepository, DraftRepository
from app.repositories.factory import get_story_repo, get_draft_repo
from app.jobs.drafting_job import run_draft_generation

logger = logging.getLogger(__name__)
router = APIRouter(tags=["drafts"])


class EditDraftBody(BaseModel):
    edited_text: str


class PublishDraftBody(BaseModel):
    x_url: Optional[str] = None


@router.post("/api/stories/{story_id}/draft")
def create_draft(
    story_id: str,
    force: bool = Query(False, description="Regenerate even if the draft was already edited or posted"),
    story_repo: StoryRepository = Depends(get_story_repo),
    draft_repo: DraftRepository = Depends(get_draft_repo)
):
    """Generates (or regenerates) a rule-based draft post for a story."""
    try:
        draft = run_draft_generation(story_repo, draft_repo, story_id, force_regenerate=force)
        return {"status": "success", "draft": draft.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate draft for story #{story_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate draft.")


@router.get("/api/stories/{story_id}/draft")
def get_draft_for_story(story_id: str, draft_repo: DraftRepository = Depends(get_draft_repo)):
    """Fetches the current draft for a story, if one exists."""
    draft = draft_repo.get_draft_by_story_id(story_id)
    if not draft:
        raise HTTPException(status_code=404, detail="No draft exists for this story.")
    return draft.to_dict()


@router.get("/api/drafts")
def list_drafts(
    status: str = Query("all", description="Filter by draft status: all, NEW, EDITED, POSTED, DISCARDED"),
    limit: int = Query(50, ge=1, le=100),
    draft_repo: DraftRepository = Depends(get_draft_repo)
):
    """Lists drafts, optionally filtered by status."""
    try:
        drafts = draft_repo.get_drafts(status=status, limit=limit)
        return [d.to_dict() for d in drafts]
    except Exception as e:
        logger.error(f"Error listing drafts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error listing drafts.")


@router.post("/api/drafts/{draft_id}/edit")
def edit_draft(draft_id: str, body: EditDraftBody, draft_repo: DraftRepository = Depends(get_draft_repo)):
    """Saves a manual edit to a draft's text and marks it EDITED."""
    draft = draft_repo.get_draft_by_id(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft.edited_text = body.edited_text
    draft.status = "EDITED"
    saved = draft_repo.save_draft(draft)
    return {"status": "success", "draft": saved.to_dict()}


@router.post("/api/drafts/{draft_id}/publish")
def publish_draft(draft_id: str, body: PublishDraftBody, draft_repo: DraftRepository = Depends(get_draft_repo)):
    """Marks a draft as posted, recording a PublishedPost entry."""
    try:
        published = draft_repo.mark_published(draft_id, x_url=body.x_url)
        return {"status": "success", "published_post": published.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to mark draft #{draft_id} as published: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to publish draft.")


@router.post("/api/drafts/{draft_id}/discard")
def discard_draft(draft_id: str, draft_repo: DraftRepository = Depends(get_draft_repo)):
    """Marks a draft as discarded."""
    try:
        draft = draft_repo.discard_draft(draft_id)
        return {"status": "success", "draft": draft.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to discard draft #{draft_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to discard draft.")
