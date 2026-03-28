"""
Signal endpoints — proper market closed handling, NaN-safe.
No false signals on weekends/after hours.
"""

import math
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Query
from core.cache import cache
import pytz

router = APIRouter(prefix="/api", tags=["signals"])
IST = pytz.timezone("Asia/Kolkata")


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (int, str, bool, type(None))):
        return obj
    if hasattr(obj, 'item'):
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
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return obj


def _is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 555 <= t <= 930


def _market_closed_reason() -> str:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return "Weekend — market closed. Next open Monday 9:15 AM."
    t = now.hour * 60 + now.minute
    if t < 555:
        return "Pre-market. Opens at 9:15 AM IST."
    return "After hours. Opens tomorrow 9:15 AM IST."


@router.get("/signal")
async def get_signal(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
    timeframe: str = Query("Intraday"),
):
    """Main confluence signal. Shows MARKET CLOSED when not trading."""
    if not _is_market_open():
        return _sanitize({
            "symbol": symbol, "action": "NO TRADE", "signal_label": "MARKET CLOSED",
            "confluence_score": 0, "confidence": 0, "strike": 0,
            "entry_premium": 0, "sl_premium": 0,
            "target1_premium": 0, "target2_premium": 0,
            "components": {},
            "trade": {"action": "NO TRADE", "reasoning": [_market_closed_reason()]},
            "timestamp": datetime.now(IST).strftime("%H:%M:%S"),
            "market_status": "CLOSED",
        })

    data = cache.get(f"signal:{symbol}")
    if data:
        return _sanitize(data)

    return _sanitize({
        "symbol": symbol, "action": "NO TRADE", "signal_label": "LOADING",
        "confluence_score": 0, "confidence": 0, "strike": 0,
        "entry_premium": 0, "sl_premium": 0,
        "target1_premium": 0, "target2_premium": 0,
        "components": {},
        "trade": {"action": "NO TRADE", "reasoning": ["Data loading... wait 60 seconds."]},
        "timestamp": "",
    })


@router.get("/quick-signal")
async def get_quick_signal(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
):
    """5-min scalping signal. Blocked outside market hours."""
    if not _is_market_open():
        return _sanitize({
            "has_signal": False, "action": "NO SIGNAL", "direction": "NEUTRAL",
            "reason": _market_closed_reason(),
            "strike": 0, "confidence": 0, "score": 0,
            "supertrend": {"signal": 0, "detail": "Market closed", "fresh": False},
            "vwap": {"signal": 0, "detail": "Market closed"},
            "rsi": {"signal": 0, "detail": "Market closed", "value": 50},
            "adx": 0, "agreement": "—", "risk_reward": 0,
            "macd_hist": 0, "macd_growing": False, "bb_pct": 0.5,
            "ha_confirms": False, "di_spread": 0,
            "entry_premium": 0, "sl_premium": 0,
            "target1_premium": 0, "target2_premium": 0,
            "timestamp": "",
        })

    data = cache.get(f"quick_signal:{symbol}")
    if data:
        return _sanitize(data)

    return _sanitize({
        "has_signal": False, "action": "NO SIGNAL", "direction": "NEUTRAL",
        "reason": "Data loading... wait 15 seconds.",
        "strike": 0, "confidence": 0, "score": 0,
        "supertrend": {"signal": 0, "detail": "Loading", "fresh": False},
        "vwap": {"signal": 0, "detail": "Loading"},
        "rsi": {"signal": 0, "detail": "Loading", "value": 50},
        "adx": 0, "agreement": "—", "risk_reward": 0,
        "macd_hist": 0, "macd_growing": False, "bb_pct": 0.5,
        "ha_confirms": False, "di_spread": 0,
        "entry_premium": 0, "sl_premium": 0,
        "target1_premium": 0, "target2_premium": 0,
        "timestamp": "",
    })


@router.get("/btst")
async def get_btst(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
):
    """BTST prediction. Only meaningful 2:30-3:30 PM on trading days."""
    now = datetime.now(IST)

    # Weekend — no BTST
    if now.weekday() >= 5:
        return _sanitize({
            "prediction": "WEEKEND", "emoji": "⚪",
            "score": 0, "confidence": 0,
            "factors": {}, "bullish_count": 0, "bearish_count": 0,
            "factors_with_data": 0, "total_factors": 10,
            "btst_trade": None, "gap_day_info": None,
            "timestamp": now.strftime("%H:%M:%S"),
            "market_status": "WEEKEND",
            "best_check_time": "Monday 3:00 PM IST",
        })

    data = cache.get(f"btst:{symbol}")
    if data:
        return _sanitize(data)

    # Before 2:30 PM — too early for BTST
    t = now.hour * 60 + now.minute
    if t < 870:  # 2:30 PM
        return _sanitize({
            "prediction": "TOO EARLY", "emoji": "⏳",
            "score": 0, "confidence": 0,
            "factors": {}, "bullish_count": 0, "bearish_count": 0,
            "factors_with_data": 0, "total_factors": 10,
            "btst_trade": None, "gap_day_info": None,
            "timestamp": now.strftime("%H:%M:%S"),
            "best_check_time": "3:00 PM IST today",
        })

    return _sanitize({
        "prediction": "NO DATA", "emoji": "⚪",
        "score": 0, "confidence": 0,
        "factors": {}, "bullish_count": 0, "bearish_count": 0,
        "factors_with_data": 0, "total_factors": 10,
        "btst_trade": None, "gap_day_info": None,
        "timestamp": "",
    })


@router.get("/alerts")
async def get_alerts(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
):
    data = cache.get(f"alerts:{symbol}")
    if data:
        return _sanitize(data)
    return {"symbol": symbol, "alerts": [], "exit_recommendation": None}
