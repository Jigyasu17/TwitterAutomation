# Cleaning Up the Public Vercel URL

The deployed URL is ugly because it's derived from the **Vercel project name**, which is set
once when a project is first linked (usually auto-generated from the repo name plus a random
suffix if that name was taken) and is *not* controlled by anything in this repo — `vercel.json`
has no `name` field in the current Vercel platform (that key was deprecated years ago in favor
of the dashboard/CLI project name). So this is a one-time account-side change, not a code change.

## Option A — Vercel Dashboard (safest, no CLI needed)

1. Go to the project on [vercel.com](https://vercel.com) → **Settings** → **General**.
2. Under **Project Name**, click **Edit**, enter a clean name (e.g. `marketpulse`), save.
3. Vercel immediately serves the project at `https://marketpulse.vercel.app` (or the next
   available variant, e.g. `marketpulse-<yourteam>.vercel.app`, if `marketpulse.vercel.app` is
   already taken by someone else's project).
4. The **previous** `*.vercel.app` URL stops resolving once renamed — update the URL anywhere
   it's bookmarked, shared, or hardcoded (this repo doesn't hardcode it anywhere, so nothing
   else needs to change).

## Option B — Vercel CLI

```
vercel project ls              # confirm the exact current project name
vercel project rename <new-name>
```

Requires `vercel login` first and the Vercel CLI installed (`npm i -g vercel`) — not currently
a project dependency, so only worth installing if the dashboard route above isn't preferred.

## What this does NOT affect

- **Cron jobs** (`vercel.json`'s `crons` block) — these are path-based (`/api/jobs/collect`
  etc.), not tied to the project name or domain, so renaming changes nothing about them.
- **Environment variables** (`CRON_SECRET`, `GCP_PROJECT_ID`, `FIRESTORE_CREDENTIALS_JSON`) —
  scoped to the project itself, they carry over automatically through a rename.
- **Firestore** — entirely unrelated; the Firestore project (`GCP_PROJECT_ID`) is a separate
  GCP resource, unaffected by what the Vercel project happens to be named.

## Optional next step: a custom domain

A custom domain (e.g. `marketpulse.yourdomain.com`) would be the real fix if this needs to look
fully professional, but that requires owning a domain and pointing DNS at Vercel — **not done
here**, since the brief was explicit about not buying a domain or touching DNS. If a domain is
acquired later: Vercel dashboard → **Settings** → **Domains** → **Add** → follow the DNS record
instructions Vercel shows for that specific registrar.
