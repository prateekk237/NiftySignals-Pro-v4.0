"""
Trade Manager — Trailing SL, Expiry Day, Partial Exits.
The module that turns signals into profits.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import pytz

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


# ═══════════════════════════════════════════════════════════════
#  1. TRAILING STOP-LOSS ENGINE
# ═══════════════════════════════════════════════════════════════
#
#  Stage progression:
#    ENTRY     → SL at -25% of entry (initial)
#    BREAKEVEN → when +30%, move SL to entry price (zero risk)
#    T1_TRAIL  → when +50%, move SL to +25% (lock half profit)
#    T2_TRAIL  → when +80%, move SL to +50% (lock 50% profit)
#
#  SL only moves UP, never down. Peak tracking ensures we never
#  give back more than one stage of profits.

TRAIL_STAGES = {
    "NIFTY50": {
        "breakeven_trigger": 30,    # +30% → move SL to breakeven
        "breakeven_sl": 0,          # SL at 0% (entry price)
        "t1_trigger": 50,           # +50% → lock T1
        "t1_sl": 25,               # SL at +25%
        "t2_trigger": 80,           # +80% → lock T2
        "t2_sl": 50,               # SL at +50%
        "initial_sl": -25,          # Initial SL
    },
    "BANKNIFTY": {
        "breakeven_trigger": 25,    # BN moves faster
        "breakeven_sl": 0,
        "t1_trigger": 45,
        "t1_sl": 20,
        "t2_trigger": 75,
        "t2_sl": 45,
        "initial_sl": -25,
    },
}


def compute_trailing_sl(
    entry_premium: float,
    current_ltp: float,
    highest_ltp: float,
    current_trail_stage: str,
    symbol: str = "NIFTY50",
) -> Dict:
    """
    Compute new trailing SL based on current LTP and peak.
    Returns: {trailing_sl, highest_ltp, trail_stage, should_exit, alert_type}
    """
    stages = TRAIL_STAGES.get(symbol, TRAIL_STAGES["NIFTY50"])

    # Update peak
    new_highest = max(highest_ltp or entry_premium, current_ltp)
    peak_pnl_pct = ((new_highest - entry_premium) / entry_premium) * 100
    current_pnl_pct = ((current_ltp - entry_premium) / entry_premium) * 100

    # Determine stage based on peak (not current — peak sets the floor)
    new_stage = current_trail_stage or "ENTRY"
    new_sl = entry_premium * (1 + stages["initial_sl"] / 100)

    if peak_pnl_pct >= stages["t2_trigger"]:
        new_stage = "T2_TRAIL"
        new_sl = entry_premium * (1 + stages["t2_sl"] / 100)
    elif peak_pnl_pct >= stages["t1_trigger"]:
        new_stage = "T1_TRAIL"
        new_sl = entry_premium * (1 + stages["t1_sl"] / 100)
    elif peak_pnl_pct >= stages["breakeven_trigger"]:
        new_stage = "BREAKEVEN"
        new_sl = entry_premium * (1 + stages["breakeven_sl"] / 100)

    # SL only moves up, never down
    if current_trail_stage:
        stage_order = {"ENTRY": 0, "BREAKEVEN": 1, "T1_TRAIL": 2, "T2_TRAIL": 3}
        if stage_order.get(new_stage, 0) < stage_order.get(current_trail_stage, 0):
            new_stage = current_trail_stage
            # Recalculate SL for current stage
            if current_trail_stage == "T2_TRAIL":
                new_sl = entry_premium * (1 + stages["t2_sl"] / 100)
            elif current_trail_stage == "T1_TRAIL":
                new_sl = entry_premium * (1 + stages["t1_sl"] / 100)
            elif current_trail_stage == "BREAKEVEN":
                new_sl = entry_premium * (1 + stages["breakeven_sl"] / 100)

    # Check if SL is hit
    should_exit = current_ltp <= new_sl
    alert_type = None

    if should_exit:
        if new_stage in ["T1_TRAIL", "T2_TRAIL"]:
            alert_type = "TRAIL_SL_PROFIT"  # Exiting in profit from trail
        elif new_stage == "BREAKEVEN":
            alert_type = "TRAIL_SL_BREAKEVEN"
        else:
            alert_type = "SL_HIT"

    # Stage change alert
    stage_changed = new_stage != (current_trail_stage or "ENTRY")

    return {
        "trailing_sl": round(new_sl, 1),
        "highest_ltp": round(new_highest, 1),
        "trail_stage": new_stage,
        "should_exit": should_exit,
        "alert_type": alert_type,
        "stage_changed": stage_changed,
        "current_pnl_pct": round(current_pnl_pct, 1),
        "peak_pnl_pct": round(peak_pnl_pct, 1),
    }


# ═══════════════════════════════════════════════════════════════
#  2. EXPIRY DAY INTELLIGENCE
# ═══════════════════════════════════════════════════════════════

# NSE weekly expiry = Thursday for NIFTY, Tuesday for BANKNIFTY (as of 2024)
# Monthly expiry = last Thursday
# This can change — keep configurable

WEEKLY_EXPIRY_DAY = {
    "NIFTY50": 3,      # Thursday = 3 (Mon=0)
    "BANKNIFTY": 1,     # Tuesday = 1 (new rule from late 2024)
}


def is_expiry_day(symbol: str = "NIFTY50") -> Dict:
    """
    Check if today is weekly/monthly expiry for given symbol.
    Returns adjustment parameters for signal engines.
    """
    now = datetime.now(IST)
    weekday = now.weekday()
    expiry_day = WEEKLY_EXPIRY_DAY.get(symbol, 3)

    is_weekly = weekday == expiry_day

    # Monthly expiry: last Thursday of the month
    last_day = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    last_thursday = last_day
    while last_thursday.weekday() != 3:
        last_thursday -= timedelta(days=1)
    is_monthly = now.date() == last_thursday.date()

    hour = now.hour
    minute = now.minute
    total_min = hour * 60 + minute

    # Adjustment parameters
    adjustments = {
        "is_expiry_day": is_weekly or is_monthly,
        "is_weekly_expiry": is_weekly,
        "is_monthly_expiry": is_monthly,
        "expiry_type": "MONTHLY" if is_monthly else "WEEKLY" if is_weekly else "NONE",
        "symbol": symbol,
    }

    if is_weekly or is_monthly:
        # Time-based adjustments
        if total_min >= 810:  # After 1:30 PM
            adjustments["block_new_buys"] = True
            adjustments["reason"] = "Post 1:30 PM on expiry — theta decay accelerating. No new BUY."
        elif total_min >= 720:  # After 12:00 PM
            adjustments["block_new_buys"] = False
            adjustments["tighten_targets"] = True
            adjustments["target_multiplier"] = 0.6  # 60% of normal target
            adjustments["reason"] = "Expiry day afternoon — tighter targets."
        else:
            adjustments["block_new_buys"] = False
            adjustments["tighten_targets"] = False
            adjustments["reason"] = "Expiry day morning — normal with caution."

        # Strike adjustment: prefer slightly ITM on expiry
        adjustments["strike_offset"] = -1 if is_monthly else 0  # -1 = one step ITM
        adjustments["sl_tighter"] = True
        adjustments["sl_multiplier"] = 0.8  # 20% tighter SL on expiry
    else:
        adjustments["block_new_buys"] = False
        adjustments["tighten_targets"] = False
        adjustments["reason"] = "Not expiry day."
        adjustments["strike_offset"] = 0
        adjustments["sl_tighter"] = False
        adjustments["sl_multiplier"] = 1.0

    return adjustments


# ═══════════════════════════════════════════════════════════════
#  3. PARTIAL EXIT CALCULATOR
# ═══════════════════════════════════════════════════════════════
#
#  50/25/25 rule:
#    - Exit 50% at T1 (lock guaranteed profit)
#    - Move SL to breakeven on remaining
#    - Exit 25% at T2 (bonus profit)
#    - Trail last 25% for the big move

def calculate_partial_exit(
    total_lots: int,
    exited_lots: int,
    current_pnl_pct: float,
    trail_stage: str,
) -> Optional[Dict]:
    """
    Determine if a partial exit should happen.
    Returns None if no exit needed, or {lots_to_exit, reason, remaining}.
    """
    remaining = total_lots - exited_lots
    if remaining <= 0:
        return None

    # First partial: 50% at T1
    if trail_stage == "T1_TRAIL" and exited_lots == 0:
        exit_lots = max(1, remaining // 2)
        return {
            "lots_to_exit": exit_lots,
            "reason": f"T1 HIT — Exit {exit_lots}/{total_lots} lots. Lock profit.",
            "exit_type": "PARTIAL_T1",
            "remaining_after": remaining - exit_lots,
        }

    # Second partial: 25% at T2
    if trail_stage == "T2_TRAIL" and exited_lots > 0 and remaining > 1:
        exit_lots = max(1, remaining // 2)
        return {
            "lots_to_exit": exit_lots,
            "reason": f"T2 HIT — Exit {exit_lots} more. Trail remaining {remaining - exit_lots}.",
            "exit_type": "PARTIAL_T2",
            "remaining_after": remaining - exit_lots,
        }

    return None
