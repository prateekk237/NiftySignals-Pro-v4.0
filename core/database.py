"""
Database — SQLAlchemy engine, session, and Base for BTST history.
Uses SQLite on Railway persistent volume (/data/btst_history.db).
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from core.config import settings
import logging

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# SQLite needs check_same_thread=False for multi-threaded access
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,
    pool_pre_ping=True,
)

# Enable WAL mode for better concurrent read/write
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call on startup."""
    # Import models so Base.metadata knows about all tables
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info(f"Database initialized: {settings.database_url}")
