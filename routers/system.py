"""
System admin endpoints — backup, circuit breakers, scheduler control.
Sprint 7 production hardening.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from core.cache import cache
from core.config import settings
from core.circuit_breaker import nse_breaker, yfinance_breaker, llm_breaker
import shutil, os, logging
from datetime import datetime
import pytz

router = APIRouter(prefix="/api/system", tags=["system"])
IST = pytz.timezone("Asia/Kolkata")
logger = logging.getLogger(__name__)


@router.get("/circuit-breakers")
async def get_circuit_breakers():
    """Status of all circuit breakers."""
    return {
        "breakers": [
            nse_breaker.status(),
            yfinance_breaker.status(),
            llm_breaker.status(),
        ]
    }


@router.post("/backup")
async def create_backup():
    """Create a backup of the SQLite database."""
    db_path = settings.database_url.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        raise HTTPException(404, "Database file not found")

    backup_dir = os.path.dirname(db_path) or "."
    ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"btst_backup_{ts}.db")

    try:
        shutil.copy2(db_path, backup_path)
        size = os.path.getsize(backup_path)
        logger.info(f"Database backed up: {backup_path} ({size} bytes)")
        return {
            "status": "success",
            "backup_path": backup_path,
            "size_bytes": size,
            "timestamp": ts,
        }
    except Exception as e:
        raise HTTPException(500, f"Backup failed: {str(e)}")


@router.get("/backup/download")
async def download_backup():
    """Download the current database as a file."""
    db_path = settings.database_url.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        raise HTTPException(404, "Database file not found")

    filename = f"btst_history_{datetime.now(IST).strftime('%Y%m%d')}.db"
    return FileResponse(
        db_path,
        media_type="application/octet-stream",
        filename=filename,
    )


@router.post("/cache/clear")
async def clear_cache():
    """Clear the in-memory cache."""
    removed = cache.cleanup()
    return {"status": "cleared", "expired_removed": removed, "cache": cache.status()}


@router.get("/cache/keys")
async def list_cache_keys(prefix: str = ""):
    """List all cache keys with optional prefix filter."""
    keys = cache.keys(prefix)
    return {"count": len(keys), "keys": keys[:100]}
