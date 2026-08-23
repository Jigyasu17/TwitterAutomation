# MarketPulse Cloud Architecture Map: Before vs. After

This document maps out the current local-only architecture of the MarketPulse application, identifies core structural coupling violations, and defines the target cloud-ready decoupled architecture.

---

## 1. Current Architecture & Violations Map

Currently, business modules directly import SQLAlchemy ORM models, execute SQLite queries, and rely on an in-memory scheduler thread.

### A. Current Dependency Flow
```text
FastAPI Routers / Background Jobs
       │
       ├─► Direct SQLAlchemy ORM models (Story, ResearchReport)
       ├─► Direct SQLite queries (`db.query(...)`)
       └─► In-Memory APScheduler Threads (spawns daemon workers)
```

### B. Identified Violations

#### 1. SQLAlchemy / SQL Session Leakage (Direct Database Queries)
The following files execute raw SQL database transactions directly through the `db: Session` SQLAlchemy engine instead of repositories:
- **`app/api/routes_stories.py`**:
  - `get_stories` (lines 33, 38)
  - `reject_story` (line 76)
  - `approve_story` (line 88)
  - `process_single_story` (line 122)
  - `get_story_research` (line 201)
- **`app/api/routes_stats.py`**:
  - Entire stats endpoint (lines 13, 16, 19, 25, 32)
- **`app/scheduler/jobs.py`**:
  - `run_story_processing` (line 70)
- **`app/processing/deduplication.py`**:
  - `find_duplicate_story` (lines 68, 75, 82)
  - `add_or_merge_story` (line 119)

#### 2. ORM Model Pollution in Business Logic
The following business packages import SQLAlchemy ORM models (`Story`, `ResearchReport`, etc.) directly, violating the domain-logic isolation principle:
- **`app/research/source_discovery.py`** (line 7)
- **`app/research/report_builder.py`** (line 3)
- **`app/research/orchestrator.py`** (line 6)
- **`app/processing/deduplication.py`** (line 7)
- **`app/scheduler/jobs.py`** (line 7)

#### 3. Long-Running In-Memory Scheduling
- **`app/main.py`** starts `BackgroundScheduler` inside the FastAPI lifespan startup hook. In Vercel, this thread freezes when the request completes, preventing cron operations.

#### 4. Filesystem Writing and File Logging
- **`app/main.py`** configures a `FileHandler` logging to `logs/app.log`, and triggers directory `mkdir` operations. Vercel is read-only.
- **`app/config.py`** triggers `mkdir` for `DATA_DIR` and `LOG_DIR` on initialization.

---

## 2. Target Architecture Design

We will decouple the business execution loop from SQL dependencies, establishing distinct boundary layers:

```text
API / Cron Routes
       │
       ▼
  Service Layer  ◄── [Core Business Logic & Standalone Jobs] (Uses Plain Schemas Only)
       │
       ▼
Repository Interfaces  ◄── [Python Protocol Contracts] (Zero SQL imports)
       │
       ▼
Repository Implementations
       ├─► SQL / SQLite Implementation (For local development)
       └─► [Future] Firestore Implementation (For Vercel production)
```

### A. Key Decoupled Schemas (Plain Python Data Structures)
1. **`StoryData`**: Standardizes event title, scores, category, tags, and source names.
2. **`ResearchReportData`**: Holds compiled summary report body text, status fields, and trust rating scores.
3. **`ResearchSourceData`**: Clean article URLs, publisher names, and crawler cache parameters.
4. **`ResearchFactData`**: Extracted numbers, standard currencies (USD/INR), and context string phrases.
5. **`ResearchConflictData`**: Discrepancies logs mapping mismatches and severity levels.

### B. Decoupled Standalone Jobs
Schedules are moved into standalone callable job runner modules under a new `app/jobs/` directory:
- `collection_job.py`
- `processing_job.py`
- `research_job.py`

FastAPI routes expose these job functions via API routes, which can be hit by Vercel Cron. The local scheduler (`app/scheduler/local_scheduler.py`) optionally runs them in development.
