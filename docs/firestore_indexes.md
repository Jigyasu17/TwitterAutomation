# Firestore Index Configuration

This document specifies the required composite indexes for Google Cloud Firestore.

As of the pipeline-hardening pass, `get_stories()` (`app/repositories/firestore/story_repository.py`)
only ever applies a single Firestore-side filter (`status`) plus a single Firestore-side sort field.
`category` and `priority` filtering happen in-memory on the fetched page instead of as additional
Firestore query filters. This was a deliberate simplification: the dashboard's independent status /
category / priority / sort controls can combine into dozens of distinct filter+sort shapes, and
Firestore requires a separate composite index per shape — chasing those one `FailedPrecondition` at
a time doesn't scale. Restricting the Firestore-side query to one filter + one sort field keeps the
required index set fixed and small, listed below.

---

## 1. Required Composite Indexes

| # | Collection ID | Field Path | Sort Direction | Used By | Status |
| :-- | :--- | :--- | :--- | :--- | :--- |
| 1 | **stories** | `status` <br> `final_score` | Ascending <br> Descending | `get_stories()` default (`sort_by=score`); `get_research_eligible_queue()` | Built |
| 2 | **stories** | `status` <br> `published_at` | Ascending <br> Descending | `get_stories()` with `sort_by=newest` | Defined in `firestore.indexes.json` — **still needs to be deployed/created in the live project** |
| 3 | **stories** | `status` <br> `final_score` | Ascending <br> Ascending | `get_stats()` priority-bucket counts | Built |

All three indexes above are now defined in `firestore.indexes.json` at the repo root, so it's
the single source of truth going forward instead of hand-tracking index shapes in this doc.

**Fastest fix (Firestore Console, no new tooling required):** Firestore Console → Indexes →
Create Index → Collection ID `stories`, fields `status` (Ascending) then `published_at`
(Descending), query scope Collection. Production continues to work today because the dashboard
only calls `sort_by=newest` when a user explicitly picks that sort option — this is a "build
before someone clicks it" gap, not an active outage.

**Alternative (Firebase CLI):** if/when this project adopts `firebase.json` +
`firestore.rules` for CLI-driven deploys, add a `"firestore": {"indexes": "firestore.indexes.json"}`
block to `firebase.json` and run `firebase deploy --only firestore:indexes`. Deliberately not
wired up as part of this pass — introducing `firebase.json` without an accompanying, reviewed
`firestore.rules` file would be a bigger, security-rules-adjacent change than "add an index."

A 3-field index (`status`, `final_score` DESC, `published_at` DESC) was created earlier while
diagnosing the original deployment issue, before this refactor. It's no longer used by any query
and can be deleted from the Firestore console, though leaving it costs nothing but a small amount
of storage.

---

## 2. Index Creation Notes

- Single-field queries (such as queries on `article_url`, `content_hash`, or simple `status == "NEW"`) do not require composite indexes; Firestore creates single-field indexes automatically.
- `get_stories(status="any", ...)` (used internally by `find_duplicate_story` during collection) applies no filter and no sort at all — it needs no composite index.
- Collection group queries on subcollections (like the `sources` group count query in `get_stats()`) do not require composite indexes unless filtered by multiple inequalities.
- `category` and `priority` filters no longer reach Firestore as query filters, so no index is ever needed for any combination of them — they're applied in-memory in `get_stories()` after fetching a bounded page.
