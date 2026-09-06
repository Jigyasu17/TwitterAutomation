# MarketPulse — Free Automated Financial News Platform

MarketPulse is a local-first, zero-cost content automation platform designed to discover, track, and draft financial/business news. 

## Milestone 1 Implementation

In this milestone, we have built the core data-collection foundation, including:
1. **Configurable RSS Registry**: Configured inside `app/collectors/sources.json`.
2. **RSS & Google News Ingestion**: Automatically crawls, parses, sanitizes HTML, and extracts metadata.
3. **Multi-level Deduplication**:
   - **Level 1**: Exact URL matches.
   - **Level 2**: Exact hash match on normalized titles.
   - **Level 3**: Title similarity using `difflib.SequenceMatcher` looking back 7 days.
4. **SQLite Storage Layer**: Stories and multiple source links are stored locally in `data/marketpulse.db` using SQLAlchemy.
5. **FastAPI Web Services**: Simple web router serving stats and stories list JSON, and triggering manual collector syncs.
6. **Premium Front-end Dashboard**: Single-page dark mode glassmorphism interface featuring responsive grids, toast notifications, stats counters, manual sync buttons, status tabs, and filters.

---

## News-Quality & X-Generation Overhaul

Layered on top of Milestone 1 without changing its architecture:

- **Source quality tiers** (`app/processing/source_quality.py`): regulators/exchanges > established
  financial media > general business media > unrecognized sources, feeding both scoring and
  research confidence.
- **India-relevance gate** (`app/processing/relevance.py`) and **noise filter**
  (`app/processing/noise_filter.py`): down-rank or reject generic listicles, motivational fluff,
  and stories with no Indian market connection — combining title/summary/entities/event-type
  signals rather than keyword-matching alone.
- **Event-fingerprint deduplication** (Level 5 in `app/processing/deduplication.py`): clusters
  differently-worded coverage of the same underlying event (e.g. "shares rise 8%" vs. "profit
  jumps 42%") by company + event type + time window, not just title-text similarity.
- **"Why this story ranked" transparency**: every story's `scoring_breakdown` now includes x/10
  ratings (market relevance, financial materiality, India relevance, freshness, source quality,
  investor relevance) and a one-line `key_reason`, visible in the dashboard's story detail modal.
- **Hook-strategy drafting engine** (`app/drafts/engine.py`, `app/drafts/hooks.py`): generates
  multiple angle candidates per story from structured research intelligence
  (`app/research/intelligence.py`), runs them through an anti-headline-rewrite check and a quality
  scorer (`app/drafts/quality.py`), and picks the strongest — with the previous single-template
  behavior preserved as the guaranteed-safe deterministic fallback.
- **Optional AI-assisted drafting** (`app/drafts/ai_provider.py`): if `AI_PROVIDER=ollama` is
  configured with a reachable local Ollama host, one AI-generated candidate competes on equal
  footing with the deterministic angles (same quality/fact-safety checks); production works
  identically with no AI configured (`AI_PROVIDER=none`, the default).

See `docs/firestore_indexes.md` for the Firestore composite-index status and
`docs/vercel_project_rename.md` for cleaning up the public deployment URL.

---

## Windows Installation & Setup

1. **Verify Python Installation** (requires Python 3.11+):
   ```cmd
   python --version
   ```

2. **Create Python Virtual Environment**:
   ```cmd
   python -m venv .venv
   ```

3. **Activate the Virtual Environment**:
   ```cmd
   .venv\Scripts\activate
   ```

4. **Install Dependencies**:
   ```cmd
   pip install -r requirements.txt
   ```

---

## Running the Application

Start the FastAPI application with:
```cmd
python run.py
```

Once running, open your web browser and navigate to:
```text
http://127.0.0.1:8000
```

* Click the **Collect News** button in the top right to start a manual sync of all feeds.
* Stories will appear on the feed grid with their calculated stats and origin source URLs.
* Filter stories by category or status (Active, New, Approved, Rejected).

---

## Running Tests

To execute the automated unit test suite, run:
```cmd
.venv\Scripts\pytest
```
or (if virtual environment is active):
```cmd
pytest
```
