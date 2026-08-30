import os
from pathlib import Path
from dotenv import load_dotenv

# Load env variables from .env file
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    APP_NAME: str = os.getenv("APP_NAME", "MarketPulse")
    ENV: str = os.getenv("ENV", "development")
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "127.0.0.1")
    VERCEL: bool = os.getenv("VERCEL", "0") == "1"

    # DB
    DATABASE_BACKEND: str = os.getenv("DATABASE_BACKEND", "sqlite")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/marketpulse.db")

    # Firestore Cloud DB
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
    FIRESTORE_CREDENTIALS_JSON: str = os.getenv("FIRESTORE_CREDENTIALS_JSON", "")

    # Scheduler & Limits
    NEWS_FETCH_INTERVAL_MINUTES: int = int(os.getenv("NEWS_FETCH_INTERVAL_MINUTES", "15"))
    MAX_STORIES_PER_RUN: int = int(os.getenv("MAX_STORIES_PER_RUN", "100"))
    MAX_AI_STORIES_PER_DAY: int = int(os.getenv("MAX_AI_STORIES_PER_DAY", "20"))
    MIN_IMPORTANCE_SCORE: int = int(os.getenv("MIN_IMPORTANCE_SCORE", "70"))
    
    # Dev-only APScheduler controller
    START_LOCAL_SCHEDULER: bool = (os.getenv("START_LOCAL_SCHEDULER", "1") == "1") and (ENV == "development") and not VERCEL

    # Auth for the cron-triggered job endpoints (skipped when ENV == "development")
    CRON_SECRET: str = os.getenv("CRON_SECRET", "")

    # AI
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "none")
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "")

    # Brand
    ACCOUNT_NAME: str = os.getenv("ACCOUNT_NAME", "MarketPulse")
    ACCOUNT_HANDLE: str = os.getenv("ACCOUNT_HANDLE", "marketpulse")
    IMAGE_WIDTH: int = int(os.getenv("IMAGE_WIDTH", "1600"))
    IMAGE_HEIGHT: int = int(os.getenv("IMAGE_HEIGHT", "900"))

    # Directory Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    LOG_DIR: Path = BASE_DIR / "logs"

    @classmethod
    def create_dirs(cls):
        # Only create folders if running locally in development mode
        if cls.ENV == "development" and not cls.VERCEL:
            try:
                cls.DATA_DIR.mkdir(exist_ok=True, parents=True)
                cls.LOG_DIR.mkdir(exist_ok=True, parents=True)
            except Exception as e:
                print(f"Skipping directories creation: {e}")

# Instantiate config
settings = Config()
settings.create_dirs()
