# Firestore Index Configuration

This document specifies the required composite indexes for Google Cloud Firestore.

---

## 1. Required Composite Indexes

| Collection ID | Field Path | Sort Direction | Query Reason |
| :--- | :--- | :--- | :--- |
| **stories** | `status` <br> `final_score` | Ascending <br> Descending | Queries candidate research eligible queues and dashboard lists sorted by composite priority score. |
| **stories** | `status` <br> `published_at` | Ascending <br> Descending | Queries active dashboard story lists sorted by the newest publication dates. |
| **stories** | `category` <br> `final_score` | Ascending <br> Descending | Filters story lists by category and sorts them by importance/score. |
| **stories** | `category` <br> `published_at` | Ascending <br> Descending | Filters story lists by category and sorts them by publication date. |

---

## 2. Index Creation Notes

- Single-field queries (such as queries on `article_url`, `content_hash`, or simple `status == "NEW"`) do not require composite indexes; Firestore creates single-field indexes automatically.
- Collection group queries on subcollections (like `sources` group count query) do not require composite indexes unless filtered by multiple inequalities.
