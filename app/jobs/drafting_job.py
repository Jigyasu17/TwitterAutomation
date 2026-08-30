import logging
from app.repositories.interfaces import StoryRepository, DraftRepository
from app.domain.models import DraftData
from app.drafts.orchestrator import generate_draft

logger = logging.getLogger(__name__)


def run_draft_generation(
    story_repo: StoryRepository,
    draft_repo: DraftRepository,
    story_id,
    force_regenerate: bool = False
) -> DraftData:
    """
    Triggers draft generation for a single story.
    Operates strictly via repository interfaces, matching the other job runners
    (collection_job.py, processing_job.py, research_job.py). Not yet wired to a
    cron schedule — a manual trigger is the only entry point in this pass.
    """
    return generate_draft(story_repo, draft_repo, story_id, force_regenerate=force_regenerate)
