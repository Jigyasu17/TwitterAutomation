# Firestore Query Mapping Specification

This document maps all essential database queries used in MarketPulse from SQL to Google Cloud Firestore collections, filtering patterns, sorting orders, limits, and index requirements.

---

## 1. Query Map Specification

| Operation / Query Name | Current SQL Behavior | Target Firestore Collection | Fields & Filters | Ordering & Limit | Required Index |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Get Story by ID** | `SELECT * FROM stories WHERE id = :id` | `stories/{story_id}` | Direct Document lookup by Key | N/A | None |
| **Get Story by URL** | `SELECT * FROM stories WHERE article_url = :url LIMIT 1` | `stories` | `article_url` == `url` | Limit: 1 | Single-field |
| **Get Story by Title Hash** | `SELECT * FROM stories WHERE content_hash = :hash LIMIT 1` | `stories` | `content_hash` == `hash` | Limit: 1 | Single-field |
| **Get Unprocessed (NEW)** | `SELECT * FROM stories WHERE status = 'NEW'` | `stories` | `status` == `"NEW"` | None | Single-field |
| **Research Eligible Queue** | Complex SQL check (status, scores, unresearched reports, sorting) | `stories` | `status` in `["NEW", "READY_FOR_REVIEW", "APPROVED"]` and `final_score` >= `40`. *In-memory filters applied for exact criteria.* | `final_score` DESC | **Composite**: `status` [in], `final_score` [desc] |
| **Get Stories (Dashboard Feed)** | Dynamic filters (status, category, priority) | `stories` | Dynamic filters mapping `category` and `status`. Priority maps to `final_score` inequalities. | Sorts on `final_score` DESC or `published_at` DESC | **Composite** (Optional based on active filter pairings) |
| **Get Stats (Dashboard counters)** | Aggregate counts with filters | `stories` & `sources` | Native count queries matching active collections (e.g. `status` == `"REJECTED"`) | `.count().get()` | Single-field or implicit index |
| **Get Report by Story ID** | `SELECT * FROM research_reports WHERE story_id = :story_id` | `research_reports` | `story_id` == `story_id` | Limit: 1 | Single-field |
| **Get Sources for Report** | `SELECT * FROM research_sources WHERE report_id = :report_id` | `research_reports/{report_id}/sources` | Subcollection documents | None | None |
| **Get Unresolved Conflicts** | `SELECT * FROM research_conflicts WHERE report_id = :report_id AND status = 'OPEN'` | `research_reports/{report_id}/conflicts` | Subcollection: `status` == `"OPEN"` | None | Single-field |

---

## 2. In-Memory Filter Strategy for Compound Inequalities

Firestore does not permit inequality range filters (e.g. `>` or `<`) across multiple different fields in a single query.
- In MarketPulse, the research eligibility engine selects stories where `importance_score >= min_importance OR postability_score >= min_postability`.
- **Query Resolution**: The repository fetches the candidate list of events with `status in ["NEW", "READY_FOR_REVIEW", "APPROVED"]` where `final_score >= 40` (since `final_score` is a composite of importance and postability). It then applies in-memory validations to confirm if either importance or postability score exceeds thresholds, and ensures a completed research report does not already exist. This protects Firestore from indexing errors and keeps read costs at a minimum.
