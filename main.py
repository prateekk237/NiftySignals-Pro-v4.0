"""
╔══════════════════════════════════════════════════════════════╗
║  NIFTY SIGNALS PRO v4.0 — FastAPI Backend                    ║
║  WebSocket + APScheduler + SQLite + All Python Services      ║
╚══════════════════════════════════════════════════════════════╝
"""

import logging
import socketio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler

from core.config import settings
from core.database import init_db
from core.cache import cache
from schedulers.jobs import setup_scheduler
from ws import sio

# ── Routers ───────────────────────────────────────────────────
from routers.market import router as market_router
from routers.signals import router as signals_router
from routers.positions import router as positions_router
from routers.candles import router as candles_router
from routers.strikes import router as strikes_router
from routers.api_keys import router as api_keys_router
from routers.system import router as system_router
from routers.signals_accuracy import router as accuracy_router

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Quiet down noisy libraries
for lib in ["yfinance", "urllib3", "httpx", "apscheduler.executors"]:
    logging.getLogger(lib).setLevel(logging.WARNING)

# ── APScheduler ───────────────────────────────────────────────
scheduler = BackgroundScheduler(
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 30}
)


# ── Lifespan ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # STARTUP
    logger.info("=" * 60)
    logger.info("  NiftySignals Pro v4.0 — Starting up...")
    logger.info("=" * 60)

    # 1. Init database
    init_db()
    logger.info("Database initialized")

    # 2. Load LLM API keys from DB
    from services.llm_service import llm_service
    llm_service.load_keys_from_db()
    logger.info(f"LLM providers loaded: {len(llm_service.providers)} active")

    # 3. Setup and start scheduler
    setup_scheduler(scheduler)
    scheduler.start()
    logger.info(f"APScheduler started with {len(scheduler.get_jobs())} jobs")

    # 3. Log config
    logger.info(f"CORS origins: {settings.cors_origins_list}")
    logger.info(f"LLM enabled: {settings.enable_llm}")
    logger.info(f"Database: {settings.database_url}")
    logger.info("=" * 60)

    yield

    # SHUTDOWN
    logger.info("Shutting down...")
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")
    logger.info("Shutdown complete")


# ── FastAPI App ───────────────────────────────────────────────
app = FastAPI(
    title="NiftySignals Pro API",
    version="4.0.0",
    description="Real-time Indian F&O trading signal API",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Error Handling Middleware ─────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)[:200]},
    )


# ── Register Routers ─────────────────────────────────────────
app.include_router(market_router)
app.include_router(signals_router)
app.include_router(positions_router)
app.include_router(candles_router)
app.include_router(strikes_router)
app.include_router(api_keys_router)
app.include_router(system_router)
app.include_router(accuracy_router)


# ── Health Endpoint ───────────────────────────────────────────
@app.get("/health")
async def health():
    """Health check — scheduler, cache, circuit breakers, LLM providers."""
    from services.llm_service import llm_service as _llm
    from core.circuit_breaker import nse_breaker, yfinance_breaker, llm_breaker

    jobs = [{"id": j.id, "next_run": str(j.next_run_time) if j.next_run_time else None}
            for j in scheduler.get_jobs()]

    return {
        "status": "healthy",
        "version": "4.0.0",
        "scheduler": {"running": scheduler.running, "job_count": len(jobs), "jobs": jobs},
        "cache": cache.status(),
        "database": settings.database_url.split("///")[-1] if "sqlite" in settings.database_url else "connected",
        "llm_enabled": settings.enable_llm,
        "llm_providers": _llm.providers,
        "circuit_breakers": [nse_breaker.status(), yfinance_breaker.status(), llm_breaker.status()],
    }


# ── Mount Socket.IO as ASGI app ──────────────────────────────
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)


# ── Entrypoint ────────────────────────────────────────────────
# For Railway: `uvicorn main:socket_app --host 0.0.0.0 --port $PORT`
# socket_app serves both HTTP (FastAPI) and WebSocket (Socket.IO)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:socket_app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
        log_level="info",
    )
