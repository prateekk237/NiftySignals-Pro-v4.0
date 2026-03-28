"""
Candles endpoint — initial chart load data.
Returns OHLCV data for TradingView Lightweight Charts.
"""

from fastapi import APIRouter, Query, HTTPException
from core.cache import cache
from services.data_fetcher import data_fetcher
from core.config import TIMEFRAMES

router = APIRouter(prefix="/api", tags=["candles"])


@router.get("/candles")
async def get_candles(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
    interval: str = Query("15m", description="5m, 15m, 1h, 1d"),
):
    """
    OHLCV candle data for initial chart render.
    TradingView Lightweight Charts expects:
    [{time, open, high, low, close, volume}, ...]
    """
    # Try cache first
    cache_key = f"candles:{symbol}:{interval}"
    cached = cache.get(cache_key)
    if cached:
        return {"symbol": symbol, "interval": interval, "candles": cached}

    # Resolve period from interval
    period_map = {"5m": "5d", "15m": "10d", "1h": "1mo", "1d": "6mo"}
    period = period_map.get(interval, "10d")

    df = await data_fetcher.fetch_ohlcv(symbol, interval, period)
    if df.empty:
        raise HTTPException(404, f"No candle data for {symbol} at {interval}.")

    candles = []
    for idx, row in df.iterrows():
        candles.append({
            "time": int(idx.timestamp()),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]) if "Volume" in row and row["Volume"] > 0 else 0,
        })

    cache.set(cache_key, candles, ttl=60)
    return {"symbol": symbol, "interval": interval, "candles": candles}
