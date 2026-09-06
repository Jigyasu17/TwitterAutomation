"""
One-time retroactive duplicate reconciliation.

New-arrival deduplication (deduplication.py) only ever compares an incoming
article against existing stories — it has no mechanism to notice that two
ALREADY-SAVED stories would match under the current rules (e.g. because
they were created before a dedup fix existed, or before enough sibling
duplicates had arrived to link them). This module is that one-time sweep:
the exact same matching logic, applied pairwise across the existing
database instead of new-item-vs-existing.

Safety, matching the brief's explicit requirements:
1. plan_reconciliation() only reads and returns a plan — dry-run by
   default, nothing is written until execute_reconciliation() is called
   with an explicitly-approved plan.
2. Matching reuses deduplication.py's exact functions (calculate_similarity,
   has_company_conflict, _event_fingerprint_match) rather than inventing new
   rules, so anything that wouldn't merge on ingestion won't merge here
   either — including sequential IPO milestones (different event_type:
   IPO_PRICING vs IPO_ANNOUNCEMENT never satisfies the event-fingerprint's
   exact-type requirement, so they correctly stay separate).
3. The strongest/most authoritative source (by source_quality tier) becomes
   the primary's displayed representation, exactly like live-arrival
   promotion in deduplication.py.
4. Every other cluster member's sources are merged into the primary
   (URL-deduplicated) — nothing is dropped.
5. Nothing is ever deleted. A merged-away story is marked status="MERGED"
   with merged_into_id pointing at the primary; its row, its sources, and
   any research report it has stay in the database and remain directly
   queryable by ID — just excluded from the live feed going forward.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Any
from app.domain.models import StoryData, StorySourceData
from app.processing.deduplication import (
    calculate_similarity, has_company_conflict, _event_fingerprint_match,
)
from app.processing.source_quality import get_source_tier

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.8
LOOKBACK_DAYS = 7

# Statuses excluded from reconciliation entirely: a human already rejected
# these (don't resurrect them into a cluster), and an already-MERGED story
# is by definition not a candidate primary/duplicate anymore.
_EXCLUDED_STATUSES = {"REJECTED", "MERGED"}


@dataclass
class MergePlanEntry:
    primary_id: Any
    primary_title: str
    duplicate_ids: List[Any] = field(default_factory=list)
    duplicate_titles: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    @property
    def cluster_size(self) -> int:
        return 1 + len(self.duplicate_ids)


def _are_duplicates(a: StoryData, b: StoryData, lookback_days: int) -> Optional[str]:
    """
    Returns a human-readable reason if a and b should be considered
    duplicates under the CURRENT dedup rules, else None. Mirrors
    find_duplicate_story()'s Level 1-5 checks exactly, applied to two
    already-saved stories instead of new-vs-existing.
    """
    if has_company_conflict(a.title, a.summary or "", b.title, b.summary or ""):
        return None
    if a.article_url and b.article_url and a.article_url == b.article_url:
        return "identical article URL"
    if a.content_hash and b.content_hash and a.content_hash == b.content_hash:
        return "identical normalized title hash"
    sim = calculate_similarity(a.title, b.title)
    if sim >= SIMILARITY_THRESHOLD:
        return f"title similarity {sim:.2f}"
    if _event_fingerprint_match(a.title, a.summary or "", a.published_at, b, lookback_days):
        return "event fingerprint (same company + same event type, within window)"
    return None


def _choose_primary(cluster: List[StoryData]) -> StoryData:
    """
    Strongest/most authoritative wins: best source-quality tier first
    (lower number = better), then the story with the most existing
    confirming sources, then the earliest published (the original report).
    """
    def sort_key(s: StoryData):
        published = s.published_at.timestamp() if s.published_at else 0
        return (get_source_tier(s.source_name), -len(s.sources or []), published)
    return sorted(cluster, key=sort_key)[0]


def plan_reconciliation(stories: List[StoryData], lookback_days: int = LOOKBACK_DAYS) -> List[MergePlanEntry]:
    """
    DRY-RUN ONLY — reads the given stories, groups them into duplicate
    clusters via union-find over pairwise matches (bounded to pairs within
    lookback_days of each other), and returns what WOULD be merged. Never
    writes to the database.
    """
    candidates = [s for s in stories if s.status not in _EXCLUDED_STATUSES]
    n = len(candidates)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    pair_reasons = {}
    for i in range(n):
        for j in range(i + 1, n):
            a, b = candidates[i], candidates[j]
            if a.published_at and b.published_at:
                if abs((a.published_at - b.published_at).days) > lookback_days:
                    continue
            reason = _are_duplicates(a, b, lookback_days)
            if reason:
                union(i, j)
                pair_reasons[(i, j)] = reason

    groups = {}
    for idx in range(n):
        root = find(idx)
        groups.setdefault(root, []).append(idx)

    plans = []
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        cluster = [candidates[i] for i in idxs]
        primary = _choose_primary(cluster)
        duplicates = [s for s in cluster if s.id != primary.id]

        idx_by_id = {candidates[i].id: i for i in idxs}
        reasons = []
        for dup in duplicates:
            di = idx_by_id[dup.id]
            reason = next(
                (r for (pi, pj), r in pair_reasons.items() if di in (pi, pj)),
                "event cluster",
            )
            reasons.append(reason)

        plans.append(MergePlanEntry(
            primary_id=primary.id,
            primary_title=primary.title,
            duplicate_ids=[d.id for d in duplicates],
            duplicate_titles=[d.title for d in duplicates],
            reasons=reasons,
        ))
    return plans


def execute_reconciliation(story_repo, plans: List[MergePlanEntry]) -> int:
    """
    Applies a previously-reviewed plan (from plan_reconciliation): merges
    each duplicate's confirming sources into its primary (URL-deduplicated),
    promotes the primary's displayed fields to the highest-tier source in
    the cluster (same rule as live-arrival promotion), and marks each
    duplicate status="MERGED" with merged_into_id set.

    Never deletes anything — a duplicate's own row, its sources, and any
    research report stay in the database, directly queryable by ID.

    Returns the number of stories marked as merged.
    """
    merged_count = 0
    for plan in plans:
        primary = story_repo.get_by_id(plan.primary_id)
        if not primary:
            logger.warning(f"Reconciliation: primary #{plan.primary_id} not found, skipping cluster.")
            continue

        existing_source_urls = {s.url for s in primary.sources}
        best_tier = get_source_tier(primary.source_name)
        best_source = primary

        for dup_id in plan.duplicate_ids:
            dup = story_repo.get_by_id(dup_id)
            if not dup:
                continue

            for src in dup.sources:
                if src.url not in existing_source_urls:
                    primary.sources.append(StorySourceData(
                        story_id=primary.id, source_name=src.source_name,
                        url=src.url, published_at=src.published_at, title=src.title,
                    ))
                    existing_source_urls.add(src.url)
            if dup.article_url not in existing_source_urls:
                primary.sources.append(StorySourceData(
                    story_id=primary.id, source_name=dup.source_name,
                    url=dup.article_url, published_at=dup.published_at, title=dup.title,
                ))
                existing_source_urls.add(dup.article_url)

            dup_tier = get_source_tier(dup.source_name)
            if dup_tier < best_tier:
                best_tier = dup_tier
                best_source = dup

            dup.status = "MERGED"
            dup.merged_into_id = primary.id
            story_repo.save(dup)
            merged_count += 1
            logger.info(f"Reconciliation: merged story #{dup.id} ('{dup.title}') into primary #{primary.id}")

        if best_source is not primary:
            primary.title = best_source.title
            primary.source_name = best_source.source_name
            primary.source_url = best_source.source_url
            primary.summary = best_source.summary or primary.summary
            primary.image_url = best_source.image_url or primary.image_url

        story_repo.save(primary)

    return merged_count
