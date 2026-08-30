import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database.database import init_db
from app.api.routes_stories import router as stories_router
from app.api.routes_stats import router as stats_router

# Configure logging based on environment
handlers = [logging.StreamHandler()]
if settings.ENV == "development" and not settings.VERCEL:
    try:
        log_file = settings.LOG_DIR / "app.log"
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except Exception as e:
        print(f"Skipping local file logging initialization: {e}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=handlers
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events to handle DB setup and scheduler on startup."""
    logger.info("Starting up MarketPulse backend...")
    if settings.DATABASE_BACKEND == "sqlite":
        init_db()
    
    if settings.START_LOCAL_SCHEDULER:
        try:
            from app.scheduler.local_scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            logger.warning(f"Could not load local background development scheduler: {e}")
            
    yield
    
    if settings.START_LOCAL_SCHEDULER:
        try:
            from app.scheduler.local_scheduler import shutdown_scheduler
            shutdown_scheduler()
        except Exception as e:
            logger.warning(f"Could not stop local background development scheduler: {e}")
            
    logger.info("Shutting down MarketPulse backend...")

app = FastAPI(
    title=settings.APP_NAME,
    description="MarketPulse — Free Automated Financial News Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(stories_router)
app.include_router(stats_router)

from fastapi import Depends
from app.repositories.interfaces import StoryRepository
from app.repositories.factory import get_story_repo

@app.get("/api/diagnose")
@app.get("/diagnose")
async def diagnose():
    creds = settings.FIRESTORE_CREDENTIALS_JSON
    return {
        "status": "ok",
        "source": "fastapi",
        "env": settings.ENV,
        "vercel": settings.VERCEL,
        "database_backend": settings.DATABASE_BACKEND,
        "gcp_project_id": settings.GCP_PROJECT_ID or None,
        "firestore_credentials_present": bool(creds),
        "firestore_credentials_length": len(creds) if creds else 0,
        "firestore_credentials_looks_like_json": creds.strip().startswith("{") if creds else None,
    }

# Mount static frontend directory (development only)
if settings.ENV == "development" and not settings.VERCEL:
    static_dir = Path(__file__).resolve().parent.parent / "public"
    try:
        static_dir.mkdir(exist_ok=True, parents=True)
        (static_dir / "css").mkdir(exist_ok=True, parents=True)
        (static_dir / "js").mkdir(exist_ok=True, parents=True)
    except Exception as e:
        logger.warning(f"Could not construct static folder paths locally: {e}")
        
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

# TEMPORARY ROUTING DIAGNOSTIC — remove once /api/* is confirmed working on Vercel.
# Registered last so it only catches requests that no route above already matched.
# Reveals the exact ASGI scope path Vercel's function adapter hands to Starlette,
# since production requests to registered routes (e.g. /api/stories) are currently
# returning a generic 404 as if no route matches at all.
@app.api_route("/{full_path:path}", methods=["GET", "POST"])
async def debug_catch_all(full_path: str, request: Request):
    return {
        "caught_by": "catch_all",
        "full_path_param": full_path,
        "scope_path": request.scope.get("path"),
        "raw_path": request.scope.get("raw_path", b"").decode("utf-8", "replace"),
        "method": request.method,
        "query_params": dict(request.query_params),
    }
