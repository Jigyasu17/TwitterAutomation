from fastapi import Header, HTTPException, status
from app.config import settings


def verify_cron_auth(authorization: str = Header(None)):
    """Restricts cron-triggered job endpoints to Vercel Cron invocations.

    Vercel automatically sends `Authorization: Bearer <CRON_SECRET>` on every
    cron invocation once CRON_SECRET is set as a project environment variable.
    """
    if settings.ENV == "development":
        return
    expected = f"Bearer {settings.CRON_SECRET}"
    if not settings.CRON_SECRET or authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized cron request")


def verify_admin_auth(authorization: str = Header(None)):
    """Restricts manual mutating endpoints to callers holding ADMIN_SECRET."""
    if settings.ENV == "development":
        return
    expected = f"Bearer {settings.ADMIN_SECRET}"
    if not settings.ADMIN_SECRET or authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized request")
