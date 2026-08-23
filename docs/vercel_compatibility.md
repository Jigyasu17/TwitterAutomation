# Vercel Serverless Compatibility Report

This document evaluates the compatibility of the MarketPulse python backend dependencies and execution logic under a Vercel Serverless environment.

---

## 1. Compatibility Matrix

| Category | Component / Library | Status | Description | Action Required |
| :--- | :--- | :--- | :--- | :--- |
| **Logic** | Text normalizers, Scorer, Verifier | **COMPATIBLE** | Stateless, pure python operations. | None. |
| **Parsing** | Feedparser, Trafilatura, BeautifulSoup | **COMPATIBLE** | Runs cleanly within serverless functions. | None (Timeouts are already configured to protect thread limits). |
| **Scheduling** | APScheduler Background threads | **MUST REPLACE** | Background thread runs freeze immediately when the serverless function finishes executing. | Replaced with standalone job endpoints (`/api/jobs/*`) triggered externally via Vercel Cron. |
| **Database** | SQLite Engine | **MUST REPLACE** | Serverless filesystem is read-only. SQLite local file writes will crash on execution. | Replace `sqlite/` repositories adapter with a `firestore/` repository adapter in Phase 2. |
| **Logging** | File logging (`app.log`) | **MUST REPLACE** | Cannot write log files locally. | Standardized stdout `StreamHandler` configuration for Vercel console capture. |
| **Filesystem** | Local folders creation (`mkdir`) | **POTENTIALLY PROBLEMATIC** | Dynanically calling `mkdir` in read-only folders throws exceptions. | Wrapped startups folders creations with try-catch triggers to bypass failure states in production. |
| **Static files** | StaticFiles mount router | **POTENTIALLY PROBLEMATIC** | Routing static folders via python serverless increases startup cold times and execution fees. | Configure `vercel.json` to route `/static` requests directly via Vercel Global Edge Network CDN. |

---

## 2. Serverless Execution Guardrails

When executing on Vercel (free tier limits: 10-second timeout, hobby: 60-second timeout):
- **Dynamic Crawler Timeouts**: Ensure all dynamic crawls use tight connection limits (e.g. `timeout=5`).
- **Concurrent batch processes**: Concurrency limits for batch jobs (e.g. `/api/jobs/research?concurrency=1`) must be controlled to prevent execution runs from exceeding serverless time ceilings.
