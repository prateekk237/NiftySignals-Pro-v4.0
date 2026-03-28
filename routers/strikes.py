"""
Strikes endpoint — available strikes with LTPs for autocomplete.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from core.cache import cache
from services.data_fetcher import data_fetcher

router = APIRouter(prefix="/api", tags=["strikes"])


@router.get("/strikes")
async def get_strikes(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
    type: str = Query("CE", pattern="^(CE|PE)$", description="CE or PE"),
    expiry: Optional[str] = Query(None, description="Specific expiry date"),
):
    """
    Available strikes with live LTPs.
    Used for StrikeSelector dropdown on frontend.
    """
    oc = cache.get(f"option_chain:{symbol}")
    if not oc:
        raise HTTPException(404, f"No option chain data for {symbol}.")

    oc_df = oc["df"]
    meta = oc["meta"]

    # Use nearest expiry if not specified
    target_expiry = expiry or (meta.get("expiry_dates", [""])[0])
    if not target_expiry:
        raise HTTPException(404, "No expiry dates available.")

    filtered = oc_df[oc_df["expiry"] == target_expiry].copy()
    if filtered.empty:
        raise HTTPException(404, f"No data for expiry {target_expiry}.")

    # Get current price for ATM reference
    price_data = cache.get(f"price:{symbol}")
    underlying = price_data["price"] if price_data else meta.get("underlying_value", 0)
    step = 50 if symbol == "NIFTY50" else 100
    atm = data_fetcher.get_atm_strike(underlying, step)

    # Build strike list: +-15 strikes around ATM
    range_strikes = filtered[
        (filtered["strike"] >= atm - 15 * step) &
        (filtered["strike"] <= atm + 15 * step)
    ].sort_values("strike")

    ltp_col = "ce_ltp" if type == "CE" else "pe_ltp"
    iv_col = "ce_iv" if type == "CE" else "pe_iv"
    oi_col = "ce_oi" if type == "CE" else "pe_oi"

    strikes = []
    for _, row in range_strikes.iterrows():
        strikes.append({
            "strike": int(row["strike"]),
            "ltp": round(float(row[ltp_col]), 2),
            "iv": round(float(row[iv_col]), 2),
            "oi": int(row[oi_col]),
            "is_atm": int(row["strike"]) == atm,
        })

    return {
        "symbol": symbol,
        "type": type,
        "expiry": target_expiry,
        "expiry_dates": meta.get("expiry_dates", []),
        "atm_strike": atm,
        "underlying": underlying,
        "strikes": strikes,
    }
