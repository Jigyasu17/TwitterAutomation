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
