# MarketPulse Security Integration Checklist

**Status: implemented.** Every mutating endpoint below requires an `Authorization: Bearer <token>` header in production; nothing is exposed unauthenticated except explicitly read-only routes.

---

## 1. Protected Endpoints

### A. Standalone Cron Jobs — `verify_cron_auth` (`CRON_SECRET`)
- `GET/POST /api/jobs/collect`, `/api/jobs/process`, `/api/jobs/research`
- Sent automatically by Vercel Cron as `Authorization: Bearer <CRON_SECRET>` once the env var is set on the project — never seen or typed by a human.

### B. Manual Dashboard-Triggered Endpoints — `verify_admin_auth` (`ADMIN_SECRET`)
- `POST /api/collect`, `POST /api/process`
- `POST /api/stories/{story_id}/approve`, `.../reject`, `.../process`
- `POST /api/stories/{story_id}/research`, `.../research-again`
- `POST /api/research/process`
- `POST /api/stories/{story_id}/draft` (generate/regenerate)
- `POST /api/drafts/{draft_id}/edit`, `.../publish`, `.../discard`

*Abuse risk if unprotected*: anyone with the URL could trigger crawls, spam research requests, flip story statuses, or publish/discard drafts.

### C. Intentionally open (read-only, no mutation)
`GET /api/stories`, `GET /api/stats`, `GET /api/research/queue`, `GET /api/stories/{story_id}/research`, `GET /api/stories/{story_id}/draft`, `GET /api/drafts`, `GET /api/diagnose`.

---

## 2. Authentication mechanics

Both `verify_cron_auth` and `verify_admin_auth` (`app/api/auth.py`) are skipped entirely when `settings.ENV == "development"` — local iteration needs no token. In production, each checks `Authorization: Bearer <value>` against its respective env var (`CRON_SECRET` / `ADMIN_SECRET`), 401s otherwise.

**Dashboard (browser-side)**: `public/js/dashboard.js`'s `authedFetch()` wraps every mutating call (collect, process, approve, reject, research trigger/rerun, draft generate/edit/publish/discard). It sends `Authorization: Bearer <token>` from that browser's `localStorage`; on a `401` it prompts once for the token and remembers it. The token is never embedded in the shipped JS file itself (served publicly from the CDN, viewable by anyone) — it only ever lives in the browser of whoever the operator gives it to.

This is a stopgap appropriate for a single-operator dashboard, not a multi-user auth system: anyone holding the token can act as admin, with no per-user audit trail or revocation. If this ever needs multiple distinguishable users, replace it with a real login/session mechanism rather than extending the shared-secret model further.

## 3. Deployment checklist

Before going live, set in Vercel's production environment variables:
- `CRON_SECRET` — any long random value; Vercel Cron picks it up automatically once set.
- `ADMIN_SECRET` — any long random value; share it out-of-band (not in chat/email in plaintext if avoidable) with whoever operates the dashboard.

Without `ADMIN_SECRET` set, `verify_admin_auth` fails closed (rejects every request) rather than silently allowing access — a missing secret is a hard 401, never an open door.
