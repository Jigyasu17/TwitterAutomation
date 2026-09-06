import logging
from typing import List
from app.repositories.interfaces import StoryRepository
from app.processing.reconciliation import plan_reconciliation, execute_reconciliation, MergePlanEntry

logger = logging.getLogger(__name__)


def run_reconciliation_dry_run(story_repo: StoryRepository, lookback_days: int = 7) -> List[MergePlanEntry]:
    """
    Read-only: fetches all non-rejected/non-merged stories and returns the
    duplicate clusters the CURRENT dedup rules would form — no writes.
    A one-time, occasional operation (not part of the regular collection/
    processing cron cycle), so a generous limit is appropriate here, unlike
    the recency-bounded pool used for live ingestion-time dedup.
    """
    stories = story_repo.get_stories(status="any", limit=5000)
    plans = plan_reconciliation(stories, lookback_days=lookback_days)
    logger.info(
        f"Reconciliation dry-run: {len(stories)} stories scanned, "
        f"{len(plans)} duplicate cluster(s) found, "
        f"{sum(len(p.duplicate_ids) for p in plans)} stories would be merged."
    )
    return plans


def run_reconciliation(story_repo: StoryRepository, plans: List[MergePlanEntry]) -> int:
    """Applies a previously-reviewed plan. See execute_reconciliation() for the exact, non-destructive merge behavior."""
    merged_count = execute_reconciliation(story_repo, plans)
    logger.info(f"Reconciliation executed: {merged_count} stories marked MERGED across {len(plans)} cluster(s).")
    return merged_count
