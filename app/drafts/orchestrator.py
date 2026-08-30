import logging
from app.repositories.interfaces import StoryRepository, DraftRepository
from app.domain.models import DraftData
from app.drafts.builder import generate_post_text

logger = logging.getLogger(__name__)


def generate_draft(
    story_repo: StoryRepository,
    draft_repo: DraftRepository,
    story_id,
    force_regenerate: bool = False
) -> DraftData:
    """
    Generates (or regenerates) a draft post for a story using rule-based templates.

    Idempotent like research_story() in app/research/orchestrator.py: once a draft
    has been edited or posted, regeneration is blocked unless explicitly forced, so
    a re-click never silently wipes a manual edit or posting history.
    """
    story = story_repo.get_by_id(story_id)
    if not story:
        raise ValueError(f"Story #{story_id} not found")

    existing = draft_repo.get_draft_by_story_id(story_id)
    if existing and existing.status in {"EDITED", "POSTED"} and not force_regenerate:
        logger.info(f"Draft for story #{story_id} already {existing.status}; skipping regeneration.")
        return existing

    post_text, thread_json, image_headline, image_subheadline = generate_post_text(story)

    draft = DraftData(
        id=existing.id if existing else None,
        story_id=story.id,
        post_text=post_text,
        thread_json=thread_json,
        image_headline=image_headline,
        image_subheadline=image_subheadline,
        status="NEW"
    )
    saved = draft_repo.save_draft(draft)
    logger.info(f"Draft generated for story #{story_id} (Draft #{saved.id})")
    return saved
