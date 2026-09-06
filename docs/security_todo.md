# MarketPulse Security Integration Checklist

**Status: cron-only auth.** Manual dashboard-triggered endpoints were protected by an `ADMIN_SECRET` bearer token for one deployment, then deliberately reverted at the operator's request (2026-09-06) because the prompt-for-token flow was getting in the way of normal dashboard use. Only the standalone cron endpoints remain authenticated.

---

## 1. Protected Endpoints

### A. Standalone Cron Jobs — `verify_cron_auth` (`CRON_SECRET`)
- `GET/POST /api/jobs/collect`, `/api/jobs/process`, `/api/jobs/research`
- Sent automatically by Vercel Cron as `Authorization: Bearer <CRON_SECRET>` once the env var is set on the project — never seen or typed by a human.

### B. Manual Dashboard-Triggered Endpoints — no auth
- `POST /api/collect`, `POST /api/process`
- `POST /api/stories/{story_id}/approve`, `.../reject`, `.../process`
- `POST /api/stories/{story_id}/research`, `.../research-again`
- `POST /api/research/process`
- `POST /api/stories/{story_id}/draft` (generate/regenerate)
- `POST /api/drafts/{draft_id}/edit`, `.../publish`, `.../discard`

**Accepted risk**: anyone who has (or finds/guesses) the production URL can call any of these with no login — trigger crawls, spam research requests, flip story statuses, or publish/discard drafts. There is no other protection layer in front of this URL (no Vercel password protection, no IP allowlist). This is a conscious trade-off for a single-operator, low-friction dashboard, not an oversight.

### C. Intentionally open (read-only, no mutation)
`GET /api/stories`, `GET /api/stats`, `GET /api/research/queue`, `GET /api/stories/{story_id}/research`, `GET /api/stories/{story_id}/draft`, `GET /api/drafts`, `GET /api/diagnose`.

---

## 2. Authentication mechanics

`verify_cron_auth` (`app/api/auth.py`) is skipped entirely when `settings.ENV == "development"`. In production it checks `Authorization: Bearer <value>` against `CRON_SECRET`, 401s otherwise.

Manual dashboard endpoints have no `Depends(...)` auth check at all — `public/js/dashboard.js` calls them with plain `fetch()` (its `authedFetch()` helper is now just a passthrough, kept only so call sites didn't need renaming).

## 3. Deployment checklist

Before going live, set in Vercel's production environment variables:
- `CRON_SECRET` — any long random value; Vercel Cron picks it up automatically once set. Without it set, `verify_cron_auth` fails closed (rejects every request) rather than silently allowing access.

## 4. If this needs to be re-secured later

If the dashboard URL ever leaks or gets indexed/shared, or if this moves to a multi-user setup, re-add a token check on section B's endpoints. The prior implementation (restored then reverted in this same session) is recoverable from git history — see the commit that reverts admin auth for the exact shape (`verify_admin_auth` in `app/api/auth.py`, `dependencies=[Depends(verify_admin_auth)]` on each route, and the `authedFetch`/`localStorage` prompt flow in `dashboard.js`). A lower-friction alternative worth considering instead of reintroducing a prompt: Vercel's built-in **Deployment Protection** (dashboard → Settings → Deployment Protection), which password-gates the entire URL at the platform level with no app code involved.
