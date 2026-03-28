"""
Market data endpoints — all read from cache.
v4.2: Proper market-closed handling, numpy NaN-safe, last-close data.
"""

import math
from datetime import datetime
from fastapi import APIRouter, Query
from typing import Optional, Any
from core.cache import cache
import pytz

router = APIRouter(prefix="/api", tags=["market"])
IST = pytz.timezone("Asia/Kolkata")


def _sanitize(obj: Any) -> Any:
    """Replace NaN/Inf with None — handles numpy scalars too."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (int, str, bool, type(None))):
        return obj
    # numpy scalar types (np.float64, np.int64, etc.)
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
    # pandas Timestamp etc
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return str(obj) if obj is not None else None


def _is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 555 <= t <= 930


@router.get("/market-status")
async def market_status():
    now = datetime.now(IST)
    t = now.hour * 60 + now.minute
    wd = now.weekday()
    if wd >= 5:
        status, reason, nxt = "CLOSED", "Weekend", "Monday 9:15 AM IST"
    elif t < 555:
        status, reason, nxt = "PRE_MARKET", "Pre-market", "9:15 AM IST today"
    elif t > 930:
        status, reason, nxt = "CLOSED", "After hours", "Tomorrow 9:15 AM IST" if wd < 4 else "Monday 9:15 AM IST"
    else:
        status, reason, nxt = "OPEN", "Market hours", None
    return {"status": status, "is_open": status == "OPEN", "reason": reason,
            "next_open": nxt, "server_time": now.strftime("%H:%M:%S IST"), "weekday": now.strftime("%A")}


@router.get("/price")
async def get_price(symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$")):
    """Live spot price. Falls back to last-close when market closed."""
    data = cache.get(f"price:{symbol}")
    if data:
        return _sanitize(data)

    # Try to fetch last close via yfinance (one-shot)
    last = _fetch_last_close(symbol)
    if last:
        cache.set(f"price:{symbol}", last, ttl=3600)
        return _sanitize(last)

    return {"symbol": symbol, "price": 0, "change": 0, "change_pct": 0,
            "high": 0, "low": 0, "is_stale": True, "market_status": "CLOSED"}


@router.get("/vix")
async def get_vix():
    vix_live = cache.get("vix:live") or {}
    vix_analysis = cache.get("vix:analysis") or {}
    if vix_live.get("vix"):
        return _sanitize({**vix_live, **vix_analysis})

    # Fetch last VIX close
    last = _fetch_last_vix()
    if last:
        cache.set("vix:live", last, ttl=3600)
        return _sanitize(last)

    return {"vix": 0, "vix_change": 0, "market_status": "CLOSED"}


@router.get("/option-chain")
async def get_option_chain(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
    expiry: Optional[str] = None,
):
    oc = cache.get(f"option_chain:{symbol}")
    oi = cache.get(f"oi:{symbol}")
    ltp = cache.get(f"option_ltp:{symbol}")
    if not oc:
        return {"symbol": symbol, "market_status": "CLOSED", "oi_analysis": None}
    meta = oc["meta"]
    return _sanitize({"symbol": symbol, "underlying": meta.get("underlying_value", 0),
        "expiry_dates": meta.get("expiry_dates", []), "oi_analysis": oi,
        "atm_ltp": ltp, "timestamp": meta.get("timestamp", "")})


@router.get("/global")
async def get_global():
    score_data = cache.get("global:score")
    indian_idx = cache.get("global:indian_indices")
    if not score_data:
        return {"score": 0, "label": "NO DATA", "indian_indices": {}, "details": {}}
    return _sanitize({**score_data, "indian_indices": indian_idx or {}})


@router.get("/vix-history")
async def get_vix_history():
    hist = cache.get("vix:history")
    if hist is None:
        return {"chart_data": []}
    chart_data = [{"date": str(idx.date()), "close": round(float(row["Close"]), 2)}
                  for idx, row in hist.tail(60).iterrows()]
    return {"chart_data": chart_data}


@router.get("/levels")
async def get_levels(symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$")):
    cpr = cache.get(f"cpr:{symbol}") or {}
    orb = cache.get(f"orb:{symbol}") or {}
    return _sanitize({"symbol": symbol, "cpr": cpr, "orb": orb})


@router.get("/indicators")
async def get_indicators(symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$")):
    signals = cache.get(f"indicator_signals:{symbol}")
    if not signals:
        return {"symbol": symbol, "indicators": {}, "market_status": "CLOSED"}
    return _sanitize({"symbol": symbol, "indicators": signals})


# ═══════════════════════════════════════════════════════════════
#  LAST CLOSE FETCHERS — used when market is closed
# ═══════════════════════════════════════════════════════════════

def _fetch_last_close(symbol: str) -> Optional[dict]:
    """Fetch last trading day close from yfinance."""
    try:
        import yfinance as yf
        ticker = "^NSEI" if symbol == "NIFTY50" else "^NSEBANK"
        data = yf.download(ticker, period="5d", interval="1d", progress=False)
        if data.empty:
            return None
        last = data.iloc[-1]
        prev = data.iloc[-2] if len(data) >= 2 else last
        close = float(last["Close"].iloc[0]) if hasattr(last["Close"], 'iloc') else float(last["Close"])
        prev_close = float(prev["Close"].iloc[0]) if hasattr(prev["Close"], 'iloc') else float(prev["Close"])
        change = close - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0
        high = float(last["High"].iloc[0]) if hasattr(last["High"], 'iloc') else float(last["High"])
        low = float(last["Low"].iloc[0]) if hasattr(last["Low"], 'iloc') else float(last["Low"])
        return {
            "symbol": symbol, "price": round(close, 2),
            "change": round(change, 2), "change_pct": round(change_pct, 2),
            "high": round(high, 2), "low": round(low, 2),
            "is_stale": True, "market_status": "LAST_CLOSE",
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Last close fetch failed for {symbol}: {e}")
        return None


def _fetch_last_vix() -> Optional[dict]:
    """Fetch last India VIX close."""
    try:
        import yfinance as yf
        data = yf.download("^INDIAVIX", period="5d", interval="1d", progress=False)
        if data.empty:
            return None
        last = data.iloc[-1]
        prev = data.iloc[-2] if len(data) >= 2 else last
        vix = float(last["Close"].iloc[0]) if hasattr(last["Close"], 'iloc') else float(last["Close"])
        prev_vix = float(prev["Close"].iloc[0]) if hasattr(prev["Close"], 'iloc') else float(prev["Close"])
        change = ((vix - prev_vix) / prev_vix * 100) if prev_vix > 0 else 0
        return {
            "vix": round(vix, 2), "vix_change": round(change, 2),
            "market_status": "LAST_CLOSE",
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Last VIX fetch failed: {e}")
        return None


@router.get("/news")
async def get_news():
    """News sentiment — fetches fresh if cache empty."""
    cached_score = cache.get("news:score")
    cached_headlines = cache.get("news:headlines")

    if cached_score and cached_headlines:
        return _sanitize({
            "score": cached_score.get("score", 0),
            "label": cached_score.get("label", "N/A"),
            "headlines": cached_headlines[:10],
        })

    # Cache empty — fetch fresh (works 24/7, RSS feeds don't close)
    try:
        from sentiment import calculate_news_sentiment
        score, label, headlines = calculate_news_sentiment()
        cache.set("news:score", {"score": score, "label": label}, ttl=300)
        cache.set("news:headlines", headlines, ttl=300)
        return _sanitize({
            "score": score, "label": label,
            "headlines": headlines[:10],
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"News fetch failed: {e}")
        return {"score": 0, "label": "NO DATA", "headlines": []}
