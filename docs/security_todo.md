# MarketPulse Security Integration Checklist

This document logs all endpoints that must be secured before deploying the application publicly to the cloud. **Status: implemented** — see `app/api/auth.py` for the two dependency functions and `app/api/routes_stories.py` for where they're wired in.

---

## 1. High-Risk Protected Endpoints

The following API paths modify state or trigger internet-bound crawlers and are now locked down:

### A. Standalone Cron Jobs — protected by `verify_cron_auth`
- `GET/POST /api/jobs/collect`
- `GET/POST /api/jobs/process`
- `GET/POST /api/jobs/research`
- *Abuse Risk*: Public users triggering infinite loops, scraping resources, and inflating execution costs.

### B. Manual Event Management — protected by `verify_admin_auth`
- `POST /api/stories/{story_id}/approve`
- `POST /api/stories/{story_id}/reject`
- `POST /api/stories/{story_id}/process`
- *Abuse Risk*: Unauthorized actors modifying story queues or approving invalid items.

### C. Manual Research Triggers — protected by `verify_admin_auth`
- `POST /api/stories/{story_id}/research`
- `POST /api/stories/{story_id}/research-again`
- `POST /api/research/process`
- *Abuse Risk*: Users spamming research loops, crawling target URLs repeatedly, and violating domain-rate limits.

### D. Manual Legacy Triggers — protected by `verify_admin_auth`
- `POST /api/collect`
- `POST /api/process`
- *Abuse Risk*: Same as the standalone job endpoints above — these are the manual/dashboard-button equivalents of the cron jobs and carry the same abuse risk, so they get the admin secret instead of the cron secret (a caller other than Vercel Cron is expected to use them).

Left intentionally open (read-only, no mutation): `GET /api/stories`, `GET /api/stats`, `GET /api/research/queue`, `GET /api/stories/{story_id}/research`, `GET /api/diagnose`.

---

## 2. Authentication — implemented

### A. Protecting Schedulers (Vercel Cron Tokens)
`CRON_SECRET` is an environment variable (see `.env.example`). Vercel Cron automatically sends
`Authorization: Bearer <CRON_SECRET>` on every cron invocation once the variable is set on the
Vercel project — confirmed directly against Vercel's current cron-jobs documentation. The
dependency function `verify_cron_auth` in `app/api/auth.py` checks this header, skipped entirely
when `settings.ENV == "development"`.

### B. Protecting Admin Manual Actions (Admin Secret)
`ADMIN_SECRET` is a separate environment variable, checked by `verify_admin_auth` in
`app/api/auth.py` against the same `Authorization: Bearer <value>` header shape. Any caller
(the dashboard, a script, curl) must send the matching value to reach a mutating endpoint in
production. Also skipped when `settings.ENV == "development"`.

### C. Dashboard buttons (browser-side)
`public/js/dashboard.js` wraps every mutating button's `fetch()` call (collect, process, approve,
reject, research trigger/rerun) in an `authedFetch()` helper. It sends `Authorization: Bearer
<token>` using a token cached in that browser's `localStorage`; on a `401` it prompts once for the
token and remembers it for next time. The token is never embedded in the shipped JS file itself
(which is served publicly from the CDN and can be viewed by anyone) — it only ever lives in the
browser of whoever the operator gives it to.

This is a stopgap appropriate for a single-operator dashboard, not a real multi-user auth system:
anyone who has the token can act as admin, and there's no per-user audit trail. If this ever needs
multiple distinguishable users or revocable access, replace this with a real login/session
mechanism instead of extending the shared-secret model further.
