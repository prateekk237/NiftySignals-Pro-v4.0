"""
Signal endpoints — confluence signal, quick signal, BTST prediction.
All read from cache. Return proper defaults when market closed.
"""

import math
from typing import Any
from fastapi import APIRouter, Query
from core.cache import cache

router = APIRouter(prefix="/api", tags=["signals"])


def _sanitize(obj: Any) -> Any:
    """Replace NaN/Inf with None — handles numpy types too."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (int, str, bool, type(None))):
        return obj
    if hasattr(obj, 'item'):  # numpy scalar
        try:
            v = obj.item()
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            return v
        except Exception:
            return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


@router.get("/signal")
async def get_signal(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
    timeframe: str = Query("Intraday"),
):
    """Main confluence signal."""
    data = cache.get(f"signal:{symbol}")
    if data:
        return _sanitize(data)
    return _sanitize({
        "symbol": symbol, "action": "NO TRADE", "signal_label": "MARKET CLOSED",
        "confluence_score": 0, "confidence": 0, "strike": 0,
        "entry_premium": 0, "sl_premium": 0,
        "target1_premium": 0, "target2_premium": 0,
        "components": {}, "trade": {"action": "NO TRADE", "reasoning": ["Market closed or data loading."]},
        "timestamp": "", "market_status": "CLOSED",
    })


@router.get("/quick-signal")
async def get_quick_signal(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
):
    """5-min scalping quick signal."""
    data = cache.get(f"quick_signal:{symbol}")
    if data:
        return _sanitize(data)
    return _sanitize({
        "has_signal": False, "action": "NO SIGNAL", "direction": "NEUTRAL",
        "reason": "Market closed or data loading.",
        "strike": 0, "confidence": 0, "score": 0,
        "supertrend": {"signal": 0, "detail": "N/A", "fresh": False},
        "vwap": {"signal": 0, "detail": "N/A"},
        "rsi": {"signal": 0, "detail": "N/A", "value": 50},
        "adx": 0, "agreement": "0/0",
        "macd_hist": 0, "macd_growing": False, "bb_pct": 0.5,
        "ha_confirms": False, "di_spread": 0, "risk_reward": 0,
        "entry_premium": 0, "sl_premium": 0,
        "target1_premium": 0, "target2_premium": 0,
        "timestamp": "",
    })


@router.get("/btst")
async def get_btst(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
):
    """BTST gap prediction."""
    data = cache.get(f"btst:{symbol}")
    if data:
        return _sanitize(data)
    return _sanitize({
        "prediction": "NO DATA", "emoji": "⚪",
        "score": 0, "confidence": 0,
        "factors": {}, "bullish_count": 0, "bearish_count": 0,
        "factors_with_data": 0, "total_factors": 10,
        "btst_trade": None, "gap_day_info": None,
        "timestamp": "", "market_status": "CLOSED",
    })


@router.get("/alerts")
async def get_alerts(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
):
    """Real-time alerts."""
    data = cache.get(f"alerts:{symbol}")
    if data:
        return _sanitize(data)
    return {"symbol": symbol, "alerts": [], "exit_recommendation": None}
