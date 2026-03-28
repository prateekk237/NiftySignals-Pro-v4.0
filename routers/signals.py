"""
Signal endpoints — confluence signal, quick signal, BTST prediction.
All read from cache.
"""

from fastapi import APIRouter, Query, HTTPException
from core.cache import cache

router = APIRouter(prefix="/api", tags=["signals"])


@router.get("/signal")
async def get_signal(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
    timeframe: str = Query("Intraday"),
):
    """Main confluence signal (from cache, populated by job_signal_60s)."""
    data = cache.get(f"signal:{symbol}")
    if not data:
        raise HTTPException(404, f"No signal data for {symbol}.")
    return data


@router.get("/quick-signal")
async def get_quick_signal(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
):
    """5-min scalping quick signal (from cache, populated by job_quick_signal_15s)."""
    data = cache.get(f"quick_signal:{symbol}")
    if not data:
        raise HTTPException(404, f"No quick signal for {symbol}.")
    return data


@router.get("/btst")
async def get_btst(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
):
    """BTST gap prediction (from cache, populated by job_btst_5m)."""
    data = cache.get(f"btst:{symbol}")
    if not data:
        raise HTTPException(404, f"No BTST data for {symbol}.")
    return data


@router.get("/alerts")
async def get_alerts(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
):
    """Real-time alerts (from cache, populated by job_alerts_15s)."""
    data = cache.get(f"alerts:{symbol}")
    if not data:
        return {"symbol": symbol, "alerts": [], "exit_recommendation": None}
    return data
