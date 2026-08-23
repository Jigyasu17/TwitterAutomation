import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
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
def run_diagnose(story_repo: StoryRepository = Depends(get_story_repo)):
    """Diagnostic endpoint to inspect Firestore connection and index status safely."""
    diagnostics = {
        "database_backend": settings.DATABASE_BACKEND,
        "gcp_project_id": settings.GCP_PROJECT_ID,
        "credentials_detected": bool(settings.FIRESTORE_CREDENTIALS_JSON),
        "credentials_length": len(settings.FIRESTORE_CREDENTIALS_JSON) if settings.FIRESTORE_CREDENTIALS_JSON else 0,
        "firestore_client_ok": False,
        "query_execution_ok": False,
        "error_log": None
    }
    
    if settings.DATABASE_BACKEND == "firestore":
        try:
            from app.repositories.firestore.client import get_firestore_client
            client = get_firestore_client()
            diagnostics["firestore_client_ok"] = True
            diagnostics["project_detected_by_client"] = client.project
            
            # Run simple query to check indexing/connectivity
            try:
                # Harmless read of 1 doc
                client.collection("stories").limit(1).get()
                diagnostics["query_execution_ok"] = True
            except Exception as query_error:
                diagnostics["error_log"] = f"Query failed: {query_error}"
                
        except Exception as conn_error:
            diagnostics["error_log"] = f"Client initialization failed: {conn_error}"
    else:
        diagnostics["error_log"] = "Database backend is set to sqlite. Bypassing Firestore diagnostics."
        
    return diagnostics

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
