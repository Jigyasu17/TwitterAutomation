import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.database.models import Base

logger = logging.getLogger(__name__)

# Connect to database (SQLite)
# Check if database is SQLite and add check_same_thread configuration
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency for obtaining a database session."""
    if settings.DATABASE_BACKEND == "firestore":
        yield None
        return

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Columns added to existing tables after their first release. SQLAlchemy's
# create_all() only creates missing *tables*, never adds columns to a table
# that already exists on disk — so a persisted local marketpulse.db predating
# a model change would otherwise throw "no such column" the first time a row
# is read. This is a deliberately lightweight substitute for a full migration
# framework (Alembic would be overkill for a single local SQLite file):
# check each column exists via PRAGMA and ALTER TABLE ADD COLUMN if missing.
_NEW_COLUMNS = [
    ("drafts", "angles_json", "TEXT"),
    ("drafts", "quality_score", "INTEGER"),
    ("drafts", "hook_strategy", "TEXT"),
    ("drafts", "ai_used", "BOOLEAN DEFAULT 0"),
    ("stories", "merged_into_id", "INTEGER"),
]


def _run_lightweight_migrations():
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    with engine.connect() as conn:
        for table, column, coltype in _NEW_COLUMNS:
            try:
                existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            except Exception:
                continue  # table doesn't exist yet — create_all() will make it with the column already
            if column in existing:
                continue
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
                conn.commit()
                logger.info(f"Migrated: added column {table}.{column}")
            except Exception as e:
                logger.warning(f"Could not add column {table}.{column}: {e}")


def init_db():
    """Initializes the database schema if it doesn't already exist."""
    try:
        Base.metadata.create_all(bind=engine)
        _run_lightweight_migrations()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise e
