"""
Market data endpoints — all read from cache (instant response).
CORRECT pattern: REST reads cache, never blocks on data fetches.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from core.cache import cache

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/price")
async def get_price(symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$")):
    """Live spot price (from cache, populated by job_price_1s)."""
    data = cache.get(f"price:{symbol}")
    if not data:
        raise HTTPException(404, f"No price data for {symbol}. Market may be closed.")
    return data


@router.get("/vix")
async def get_vix():
    """India VIX live value + analysis."""
    vix_live = cache.get("vix:live") or {}
    vix_analysis = cache.get("vix:analysis") or {}
    if not vix_live:
        raise HTTPException(404, "No VIX data available.")
    return {**vix_live, "analysis": vix_analysis}


@router.get("/option-chain")
async def get_option_chain(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
    expiry: Optional[str] = None,
):
    """Option chain data with OI analysis."""
    oc = cache.get(f"option_chain:{symbol}")
    oi = cache.get(f"oi:{symbol}")
    ltp = cache.get(f"option_ltp:{symbol}")
    if not oc:
        raise HTTPException(404, f"No option chain for {symbol}.")

    meta = oc["meta"]
    return {
        "symbol": symbol,
        "underlying": meta.get("underlying_value", 0),
        "expiry_dates": meta.get("expiry_dates", []),
        "oi_analysis": oi,
        "atm_ltp": ltp,
        "timestamp": meta.get("timestamp", ""),
    }


@router.get("/global")
async def get_global():
    """Global markets snapshot."""
    score_data = cache.get("global:score")
    indian_idx = cache.get("global:indian_indices")
    if not score_data:
        raise HTTPException(404, "No global data yet.")
    return {
        **score_data,
        "indian_indices": indian_idx or {},
    }


@router.get("/vix-history")
async def get_vix_history():
    """VIX chart data (last 60 days)."""
    hist = cache.get("vix:history")
    if hist is None:
        raise HTTPException(404, "No VIX history available.")
    chart_data = [
        {"date": str(idx.date()), "close": round(float(row["Close"]), 2)}
        for idx, row in hist.tail(60).iterrows()
    ]
    return {"chart_data": chart_data}


@router.get("/levels")
async def get_levels(symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$")):
    """CPR + ORB key levels."""
    cpr = cache.get(f"cpr:{symbol}") or {}
    orb = cache.get(f"orb:{symbol}") or {}
    return {"symbol": symbol, "cpr": cpr, "orb": orb}


@router.get("/indicators")
async def get_indicators(symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$")):
    """All indicator signals (from last signal computation)."""
    signals = cache.get(f"indicator_signals:{symbol}")
    if not signals:
        raise HTTPException(404, f"No indicator data for {symbol}.")
    return {"symbol": symbol, "indicators": signals}
