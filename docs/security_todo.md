# MarketPulse Security Integration Checklist

This document logs all endpoints that must eventually be secured before deploying the application publicly to the cloud, outlining blueprinted security mechanisms.

---

## 1. High-Risk Protected Endpoints

The following API paths modify state or trigger internet-bound crawlers and must be locked down to prevent public execution abuse:

### A. Standalone Cron Jobs
- `POST /api/jobs/collect`
- `POST /api/jobs/process`
- `POST /api/jobs/research`
- *Abuse Risk*: Public users triggering infinite loops, scraping resources, and inflating execution costs.

### B. Manual Event Management
- `POST /api/stories/{story_id}/approve`
- `POST /api/stories/{story_id}/reject`
- `POST /api/stories/{story_id}/process`
- *Abuse Risk*: Unauthorized actors modifying story queues or approving invalid items.

### C. Manual Research Triggers
- `POST /api/stories/{story_id}/research`
- `POST /api/stories/{story_id}/research-again`
- *Abuse Risk*: Users spamming research loops, crawling target URLs repeatedly, and violating domain-rate limits.

---

## 2. Authentication Blueprints

### A. Protecting Schedulers (Vercel Cron Tokens)
To secure the job endpoints, we will enforce a secret token header verification system:

1. **Config Variable**: `CRON_SECRET` (configured as an environment variable in Vercel).
2. **Execution Hook**:
   - Vercel Cron automatically includes an authorization header (e.g. `Authorization: Bearer <CRON_SECRET>`).
   - We will write a lightweight dependency check:
     ```python
     from fastapi import Header, HTTPException, status
     from app.config import settings

     def verify_cron_auth(authorization: str = Header(None)):
         if not settings.ENV == "development":
             expected = f"Bearer {settings.CRON_SECRET}"
             if not authorization or authorization != expected:
                 raise HTTPException(
                     status_code=status.HTTP_401_UNAUTHORIZED,
                     detail="Unauthorized cron request"
                 )
     ```

### B. Protecting Admin Manual Actions (Admin Secrets)
Before exposing the dashboard, we will require credential challenges:
1. **Mechanism**: Basic token authorization cookie or header challenge.
2. **Strategy**: A simple middleware checking a custom `ADMIN_SECRET` token or integrating Firebase Authentication UI bindings to restrict dashboard operations to approved user profiles.
3. **Local Dev Override**: Disable authentication when `settings.ENV == "development"`.
