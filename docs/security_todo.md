# MarketPulse Security Integration Checklist

## Current state (deliberate choice, not an oversight)

The manual/dashboard-facing endpoints below are **intentionally left open with no auth**:
- `POST /api/collect`, `POST /api/process`
- `POST /api/stories/{story_id}/approve`, `POST /api/stories/{story_id}/reject`, `POST /api/stories/{story_id}/process`
- `POST /api/stories/{story_id}/research`, `POST /api/stories/{story_id}/research-again`, `POST /api/research/process`

An `ADMIN_SECRET`-based token check was implemented and then deliberately removed at the project
owner's request — the priority right now is getting the data pipeline itself working end-to-end;
hardening the manual endpoints can come back once that's solid. *Abuse risk if this URL becomes
widely known*: anyone could trigger crawls, spam research requests, or flip story statuses. Low
practical risk today since the deployment URL is an unlisted `*.vercel.app` address, but revisit
before sharing the URL publicly or pointing a custom domain at it.

The cron job endpoints remain protected — these are never clicked by a person, so protecting them
costs no usability:
- `GET/POST /api/jobs/collect`, `/api/jobs/process`, `/api/jobs/research`

## Cron Job Auth (still active)

`CRON_SECRET` is an environment variable (see `.env.example`). Vercel Cron automatically sends
`Authorization: Bearer <CRON_SECRET>` on every cron invocation once the variable is set on the
Vercel project. The dependency function `verify_cron_auth` in `app/api/auth.py` checks this
header, skipped when `settings.ENV == "development"`.

## Re-adding manual-endpoint auth later

If/when this comes back: `app/api/auth.py` previously had a `verify_admin_auth` function mirroring
`verify_cron_auth` but checking an `ADMIN_SECRET` env var instead, wired onto each route via
`dependencies=[Depends(verify_admin_auth)]` in `app/api/routes_stories.py`. The frontend
(`public/js/dashboard.js`) had a matching `authedFetch()` wrapper that sent the token from
`localStorage` and prompted for it once on a `401`. Both are straightforward to reintroduce from
git history (see the commit that added them) once manual-endpoint hardening is prioritized again —
at that point, also consider whether a real login/session mechanism would suit better than a
shared secret, since a shared secret has no per-user audit trail or revocation.
