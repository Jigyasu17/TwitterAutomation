import logging
from app.repositories.interfaces import StoryRepository, DraftRepository
from app.domain.models import DraftData
from app.drafts.builder import generate_post_text
from app.drafts.engine import generate_draft_content

logger = logging.getLogger(__name__)


def generate_draft(
    story_repo: StoryRepository,
    draft_repo: DraftRepository,
    story_id,
    force_regenerate: bool = False
) -> DraftData:
    """
    Generates (or regenerates) a draft post for a story: hook-strategy
    selection + event-specific structure + optional AI assist, all gated by
    the anti-headline-rewrite and quality checks (see app/drafts/engine.py).

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

    try:
        result = generate_draft_content(story)
        post_text, thread_json = result.post_text, result.thread
        image_headline, image_subheadline = result.image_headline, result.image_subheadline
        angles, quality_score, hook_strategy, ai_used = result.angles, result.quality_score, result.hook_strategy, result.ai_used
        logger.info(
            f"Draft engine for story #{story_id}: hook_strategy={hook_strategy} "
            f"quality_score={quality_score} ai_used={ai_used} angles_generated={len(angles)}"
        )
    except Exception as e:
        logger.error(f"Draft engine failed for story #{story_id}, falling back to base template: {e}", exc_info=True)
        post_text, thread_json, image_headline, image_subheadline = generate_post_text(story)
        angles, quality_score, hook_strategy, ai_used = None, None, None, False

    draft = DraftData(
        id=existing.id if existing else None,
        story_id=story.id,
        post_text=post_text,
        thread_json=thread_json,
        image_headline=image_headline,
        image_subheadline=image_subheadline,
        status="NEW",
        angles=angles,
        quality_score=quality_score,
        hook_strategy=hook_strategy,
        ai_used=ai_used,
    )
    saved = draft_repo.save_draft(draft)
    logger.info(f"Draft generated for story #{story_id} (Draft #{saved.id})")
    return saved
