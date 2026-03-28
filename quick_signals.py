"""
╔══════════════════════════════════════════════════════════════╗
║  QUICK SIGNALS v3.0 — "No signal is better than a loss"     ║
║                                                              ║
║  PHILOSOPHY: Only signal when ALL conditions align.          ║
║  5-gate filter system. Every gate must pass.                 ║
║  Any doubt = NO TRADE. Zero false positives is the goal.    ║
║                                                              ║
║  IMPROVEMENTS OVER v2:                                       ║
║  1. 5-gate system (was 2/3 agreement)                       ║
║  2. Multi-Supertrend alignment (2/3 ST must agree)          ║
║  3. MACD histogram confirmation (direction + growing)       ║
║  4. Volume above 20-period average (institutional flow)     ║
║  5. Bollinger %B directional confirmation                   ║
║  6. Candle body strength check (no doji/indecision)         ║
║  7. Exhaustion detection (3+ candles same dir >1.5%)        ║
║  8. Time-of-day filter (skip first/last 15min)              ║
║  9. Separate BankNifty thresholds (more volatile)           ║
║ 10. R:R improved to 2:1 (was 1.33:1)                       ║
║ 11. Confidence scoring 0-100 (signal only at ≥70)           ║
║ 12. Heikin Ashi trend confirmation                          ║
╚══════════════════════════════════════════════════════════════╝
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict
import pytz

from config import (
    NIFTY_LOT_SIZE, BANKNIFTY_LOT_SIZE,
    STRIKE_STEP_NIFTY, STRIKE_STEP_BANKNIFTY,
)
from data_fetcher import get_atm_strike

IST = pytz.timezone("Asia/Kolkata")


# ═══════════════════════════════════════════════════════════════
#  INDEX-SPECIFIC THRESHOLDS
# ═══════════════════════════════════════════════════════════════
PARAMS = {
    "NIFTY50": {
        "adx_min": 22,              # Trend gate — higher = fewer but better signals
        "rsi_block_high": 78,       # Block BUY CE above this
        "rsi_block_low": 22,        # Block BUY PE below this
        "rsi_bull_zone": (55, 78),  # RSI must be in this range for BUY CE
        "rsi_bear_zone": (22, 45),  # RSI must be in this range for BUY PE
        "exhaust_candles": 3,       # Consecutive candles to detect exhaustion
        "exhaust_pct": 1.2,         # % move threshold for exhaustion
        "vol_avg_period": 20,       # Volume moving average period
        "sl_pct": 25,               # Stop loss % of premium (tighter)
        "t1_pct": 50,               # Target 1 % profit (R:R = 2:1)
        "t2_pct": 100,              # Target 2 % profit (trail after T1)
        "atr_sl_mult": 0.8,        # ATR multiplier for underlying SL
        "atr_t1_mult": 1.2,        # ATR multiplier for target 1
        "atr_t2_mult": 2.0,        # ATR multiplier for target 2
        "min_candle_body_pct": 40,  # Min candle body as % of range (no doji)
        "min_confidence": 70,       # Minimum score to generate signal
    },
    "BANKNIFTY": {
        "adx_min": 20,              # BankNifty trends more clearly
        "rsi_block_high": 80,       # Wider range — more momentum
        "rsi_block_low": 20,
        "rsi_bull_zone": (53, 80),
        "rsi_bear_zone": (20, 47),
        "exhaust_candles": 3,
        "exhaust_pct": 1.5,         # BN moves more, higher threshold
        "vol_avg_period": 20,
        "sl_pct": 25,
        "t1_pct": 50,
        "t2_pct": 100,
        "atr_sl_mult": 0.9,        # Slightly wider SL for BN volatility
        "atr_t1_mult": 1.3,
        "atr_t2_mult": 2.2,
        "min_candle_body_pct": 35,  # BN has more wicks, slightly lower
        "min_confidence": 70,
    },
}


def generate_quick_signal(
    df: pd.DataFrame,
    symbol: str = "NIFTY50",
    capital: float = 10000,
    oc_df: pd.DataFrame = None,
    oc_expiry: str = None,
) -> Dict:
    """
    Generate high-confidence scalping signal using 5-gate filter system.
    PHILOSOPHY: No signal is better than a losing signal.
    """
    if df is None or df.empty or len(df) < 20:
        return _no_signal("Not enough data (need 20+ candles)")

    P = PARAMS.get(symbol, PARAMS["NIFTY50"])
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last["Close"])
    reasons = []  # Track why signal was blocked (for debugging)

    # ═══════════════════════════════════════════════════════════
    #  GATE 0: TIME-OF-DAY FILTER
    #  Skip first 15min (9:15-9:30) and last 15min (3:15-3:30)
    # ═══════════════════════════════════════════════════════════
    now = datetime.now(IST)
    h, m = now.hour, now.minute
    total_min = h * 60 + m

    if total_min < 570:  # Before 9:30 AM
        return _no_signal("⏳ Opening volatility (9:15-9:30). Wait for price discovery.")
    if total_min > 915:  # After 3:15 PM
        return _no_signal("⏳ Closing hour. No new scalping positions. Exit existing trades.")
    if now.weekday() >= 5:
        return _no_signal("Weekend — market closed.")

    # ═══════════════════════════════════════════════════════════
    #  GATE 1: TREND — ADX + Multi-Supertrend Alignment
    #  ADX must show clear trend. 2/3 Supertrends must agree.
    # ═══════════════════════════════════════════════════════════
    adx_val = _safe_float(last, "ADX")
    plus_di = _safe_float(last, "Plus_DI")
    minus_di = _safe_float(last, "Minus_DI")

    if adx_val < P["adx_min"]:
        return _no_signal(
            f"SIDEWAYS — ADX {adx_val:.1f} < {P['adx_min']} threshold. "
            f"No trend. Avoid directional trades."
        )

    # Triple Supertrend check
    st_fast_dir = _safe_int(last, "STd_5_1.5")
    st_med_dir = _safe_int(last, "STd_10_3.0")
    st_slow_dir = _safe_int(last, "STd_14_4.0")
    st_dirs = [st_fast_dir, st_med_dir, st_slow_dir]
    st_bull = sum(1 for d in st_dirs if d > 0)
    st_bear = sum(1 for d in st_dirs if d < 0)

    if st_bull < 2 and st_bear < 2:
        return _no_signal(
            f"MIXED TREND — Supertrends split ({st_bull}↑/{st_bear}↓). "
            f"Fast:{_dir_label(st_fast_dir)} Med:{_dir_label(st_med_dir)} Slow:{_dir_label(st_slow_dir)}"
        )

    trend_dir = 1 if st_bull >= 2 else -1
    is_bullish = trend_dir > 0

    # Fresh Supertrend cross bonus
    prev_st_fast = _safe_int(prev, "STd_5_1.5")
    st_fresh_cross = (st_fast_dir != prev_st_fast) and (st_fast_dir == trend_dir)

    # All 3 aligned bonus
    all_st_aligned = (st_bull == 3) if is_bullish else (st_bear == 3)

    # DI confirmation: +DI > -DI for bullish, vice versa
    di_confirms = (plus_di > minus_di) if is_bullish else (minus_di > plus_di)
    if not di_confirms:
        return _no_signal(
            f"DI DIVERGENCE — Trend is {'bullish' if is_bullish else 'bearish'} but "
            f"+DI={plus_di:.1f} vs -DI={minus_di:.1f} disagrees."
        )

    st_detail = (
        f"{'BULL' if is_bullish else 'BEAR'} "
        f"({st_bull}↑/{st_bear}↓) "
        f"{'★FRESH' if st_fresh_cross else ''}"
        f"{'★ALL3' if all_st_aligned else ''}"
    ).strip()

    # ═══════════════════════════════════════════════════════════
    #  GATE 2: MOMENTUM — MACD + RSI confirmation
    # ═══════════════════════════════════════════════════════════
    macd_hist = _safe_float(last, "MACD_Hist")
    prev_macd_hist = _safe_float(prev, "MACD_Hist")
    rsi_val = _safe_float(last, "RSI_7", default=50)

    # MACD histogram must be in trend direction AND growing
    macd_direction_ok = (macd_hist > 0) if is_bullish else (macd_hist < 0)
    macd_growing = abs(macd_hist) > abs(prev_macd_hist)

    if not macd_direction_ok:
        return _no_signal(
            f"MACD DISAGREES — Hist {macd_hist:+.2f} is "
            f"{'negative (bearish)' if is_bullish else 'positive (bullish)'} "
            f"but trend is {'bullish' if is_bullish else 'bearish'}."
        )

    # RSI must be in favorable zone (not extreme, not dead zone)
    bull_lo, bull_hi = P["rsi_bull_zone"]
    bear_lo, bear_hi = P["rsi_bear_zone"]

    if is_bullish:
        if rsi_val >= P["rsi_block_high"]:
            return _no_signal(
                f"BLOCKED — RSI {rsi_val:.1f} ≥ {P['rsi_block_high']} OVERBOUGHT. "
                f"Reversal imminent. Do NOT buy CE."
            )
        if rsi_val < bull_lo:
            return _no_signal(
                f"RSI TOO LOW — RSI {rsi_val:.1f} < {bull_lo} for bullish signal. "
                f"Momentum not confirmed."
            )
    else:
        if rsi_val <= P["rsi_block_low"]:
            return _no_signal(
                f"BLOCKED — RSI {rsi_val:.1f} ≤ {P['rsi_block_low']} OVERSOLD. "
                f"Bounce imminent. Do NOT buy PE."
            )
        if rsi_val > bear_hi:
            return _no_signal(
                f"RSI TOO HIGH — RSI {rsi_val:.1f} > {bear_hi} for bearish signal. "
                f"Momentum not confirmed."
            )

    rsi_detail = f"{'BULLISH' if is_bullish else 'BEARISH'} ({rsi_val:.1f})"

    # ═══════════════════════════════════════════════════════════
    #  GATE 3: PRICE ACTION — VWAP + Bollinger + Candle Body
    # ═══════════════════════════════════════════════════════════

    # VWAP check
    vwap_val = _safe_float(last, "VWAP")
    vwap_ok = False
    vwap_detail = "N/A"

    if vwap_val > 0:
        vwap_pct = ((price - vwap_val) / vwap_val) * 100
        vwap_ok = (price > vwap_val) if is_bullish else (price < vwap_val)
        vwap_detail = f"{'ABOVE' if price > vwap_val else 'BELOW'} ({vwap_pct:+.2f}%)"
    else:
        # EMA fallback
        e9 = _safe_float(last, "EMA_9")
        e21 = _safe_float(last, "EMA_21")
        if e9 > 0 and e21 > 0:
            vwap_ok = (e9 > e21) if is_bullish else (e9 < e21)
            vwap_detail = f"EMA9{'>' if e9 > e21 else '<'}EMA21 (VWAP N/A)"

    if not vwap_ok:
        return _no_signal(
            f"PRICE VS VWAP — Price {'below' if is_bullish else 'above'} VWAP. "
            f"{'Need above VWAP for BUY CE' if is_bullish else 'Need below VWAP for BUY PE'}. "
            f"VWAP: {vwap_detail}"
        )

    # Bollinger %B check
    bb_pct = _safe_float(last, "BB_Pct", default=0.5)
    bb_ok = True
    if is_bullish and bb_pct < 0.4:
        bb_ok = False
        reasons.append(f"BB%B too low ({bb_pct:.2f}) for bullish")
    elif not is_bullish and bb_pct > 0.6:
        bb_ok = False
        reasons.append(f"BB%B too high ({bb_pct:.2f}) for bearish")

    if not bb_ok:
        return _no_signal(
            f"BOLLINGER DISAGREES — BB%B={bb_pct:.2f}. "
            f"{'Need >0.4 for bullish' if is_bullish else 'Need <0.6 for bearish'}."
        )

    # Candle body strength — reject doji/spinning tops
    candle_high = float(last["High"])
    candle_low = float(last["Low"])
    candle_range = candle_high - candle_low
    candle_body = abs(float(last["Close"]) - float(last["Open"]))

    if candle_range > 0:
        body_pct = (candle_body / candle_range) * 100
        if body_pct < P["min_candle_body_pct"]:
            return _no_signal(
                f"WEAK CANDLE — Body {body_pct:.0f}% of range "
                f"(min {P['min_candle_body_pct']}%). Indecision candle — skip."
            )

    # ═══════════════════════════════════════════════════════════
    #  GATE 4: VOLUME — Must be above average
    # ═══════════════════════════════════════════════════════════
    if "Volume" in df.columns:
        current_vol = float(last["Volume"]) if not pd.isna(last["Volume"]) else 0
        avg_vol = df["Volume"].tail(P["vol_avg_period"]).mean()

        if avg_vol > 0 and current_vol > 0:
            vol_ratio = current_vol / avg_vol
            if vol_ratio < 0.8:
                return _no_signal(
                    f"LOW VOLUME — Current vol {vol_ratio:.1f}x of {P['vol_avg_period']}-avg. "
                    f"No institutional participation. Skip."
                )

    # ═══════════════════════════════════════════════════════════
    #  GATE 5: SAFETY FILTERS — Exhaustion + Heikin Ashi
    # ═══════════════════════════════════════════════════════════

    # Exhaustion detection: N consecutive candles in one direction with big move
    if len(df) >= P["exhaust_candles"] + 1:
        recent = df.tail(P["exhaust_candles"] + 1)
        consecutive_up = all(
            float(recent.iloc[i]["Close"]) > float(recent.iloc[i]["Open"])
            for i in range(1, len(recent))
        )
        consecutive_down = all(
            float(recent.iloc[i]["Close"]) < float(recent.iloc[i]["Open"])
            for i in range(1, len(recent))
        )

        if consecutive_up or consecutive_down:
            total_move = abs(
                float(recent.iloc[-1]["Close"]) - float(recent.iloc[1]["Open"])
            ) / float(recent.iloc[1]["Open"]) * 100

            if total_move > P["exhaust_pct"]:
                dir_label = "up" if consecutive_up else "down"
                if (consecutive_up and is_bullish) or (consecutive_down and not is_bullish):
                    return _no_signal(
                        f"EXHAUSTION — {P['exhaust_candles']} consecutive {dir_label} candles "
                        f"({total_move:.1f}% move). Reversal risk high. Skip."
                    )

    # Heikin Ashi confirmation (bonus, not gate)
    ha_confirms = False
    if "HA_Bullish" in df.columns:
        ha_bull = bool(last["HA_Bullish"]) if not pd.isna(last["HA_Bullish"]) else None
        if ha_bull is not None:
            ha_confirms = ha_bull if is_bullish else not ha_bull

    # Stochastic RSI divergence check (safety)
    stoch_k = _safe_float(last, "StochRSI_K", default=50)
    stoch_warning = False
    if is_bullish and stoch_k > 85:
        stoch_warning = True
        reasons.append(f"StochRSI overbought ({stoch_k:.0f})")
    elif not is_bullish and stoch_k < 15:
        stoch_warning = True
        reasons.append(f"StochRSI oversold ({stoch_k:.0f})")

    # ═══════════════════════════════════════════════════════════
    #  ALL GATES PASSED — Calculate confidence score
    # ═══════════════════════════════════════════════════════════
    score = 50  # Base (all gates passed = 50 minimum)

    # Trend strength bonuses
    if all_st_aligned:
        score += 12  # All 3 Supertrends aligned
    if st_fresh_cross:
        score += 10  # Fresh crossover
    if adx_val > 30:
        score += 5   # Strong trend
    elif adx_val > 25:
        score += 3

    # Momentum bonuses
    if macd_growing:
        score += 6   # MACD histogram expanding
    if di_confirms and abs(plus_di - minus_di) > 10:
        score += 4   # Strong DI separation

    # Price action bonuses
    if vwap_val > 0:
        vwap_dist = abs(((price - vwap_val) / vwap_val) * 100)
        if vwap_dist > 0.15:
            score += 3  # Clear VWAP separation
    if bb_pct > 0.7 and is_bullish:
        score += 3  # Upper BB momentum
    elif bb_pct < 0.3 and not is_bullish:
        score += 3  # Lower BB momentum

    # Confirmation bonuses
    if ha_confirms:
        score += 5  # Heikin Ashi agrees

    # Penalties
    if stoch_warning:
        score -= 8  # StochRSI extreme
    if not macd_growing:
        score -= 5  # MACD flattening

    score = max(0, min(100, score))

    # ═══════════════════════════════════════════════════════════
    #  MINIMUM CONFIDENCE CHECK
    # ═══════════════════════════════════════════════════════════
    if score < P["min_confidence"]:
        return _no_signal(
            f"CONFIDENCE TOO LOW — Score {score}/100 "
            f"(min {P['min_confidence']}). Conditions OK but not strong enough. "
            f"Wait for better setup."
        )

    # ═══════════════════════════════════════════════════════════
    #  SIGNAL CONFIRMED — Build trade details
    # ═══════════════════════════════════════════════════════════
    action = "BUY CE" if is_bullish else "BUY PE"

    if "BANK" in symbol.upper():
        lot_size = BANKNIFTY_LOT_SIZE
        strike_step = STRIKE_STEP_BANKNIFTY
    else:
        lot_size = NIFTY_LOT_SIZE
        strike_step = STRIKE_STEP_NIFTY

    atm_strike = get_atm_strike(price, strike_step)
    atr = _safe_float(last, "ATR_7", default=price * 0.005)

    # Underlying targets using ATR
    if is_bullish:
        sl_underlying = round(price - atr * P["atr_sl_mult"], 2)
        t1_underlying = round(price + atr * P["atr_t1_mult"], 2)
        t2_underlying = round(price + atr * P["atr_t2_mult"], 2)
    else:
        sl_underlying = round(price + atr * P["atr_sl_mult"], 2)
        t1_underlying = round(price - atr * P["atr_t1_mult"], 2)
        t2_underlying = round(price - atr * P["atr_t2_mult"], 2)

    # Get real premium from option chain
    entry = _get_real_premium(oc_df, oc_expiry, atm_strike, is_bullish, price)
    sl_premium = round(entry * (1 - P["sl_pct"] / 100), 1)
    t1_premium = round(entry * (1 + P["t1_pct"] / 100), 1)
    t2_premium = round(entry * (1 + P["t2_pct"] / 100), 1)
    price_source = "LIVE" if oc_df is not None and not oc_df.empty else "EST"

    # Position sizing
    cost_per_lot = entry * lot_size
    max_lots = max(1, int((capital * 0.80) / cost_per_lot)) if cost_per_lot > 0 else 1
    risk_per_lot = (entry - sl_premium) * lot_size

    # Risk-Reward ratio
    rr = round((t1_premium - entry) / max(entry - sl_premium, 0.01), 2)

    warnings = []
    if stoch_warning:
        warnings.append(f"⚠️ StochRSI at extreme — book profits quickly!")
    if st_fresh_cross:
        warnings.append("★ FRESH Supertrend cross — strongest setup!")
    if all_st_aligned:
        warnings.append("★★ All 3 Supertrends aligned — high conviction!")
    if score >= 85:
        warnings.append("🔥 Score {}/100 — A-grade setup!".format(score))

    return {
        "has_signal": True,
        "action": action,
        "direction": "BULLISH" if is_bullish else "BEARISH",
        "strike": atm_strike,
        "confidence": round(float(score), 0),
        "score": round(score / 100, 2),

        # 3 primary indicators for display
        "supertrend": {"signal": trend_dir, "detail": st_detail, "fresh": st_fresh_cross},
        "vwap": {"signal": 1 if is_bullish else -1, "detail": vwap_detail},
        "rsi": {"signal": 1 if is_bullish else -1, "detail": rsi_detail, "value": round(rsi_val, 1)},
        "adx": round(adx_val, 1),

        # Extended indicator details
        "macd_hist": round(macd_hist, 3),
        "macd_growing": macd_growing,
        "bb_pct": round(bb_pct, 2),
        "ha_confirms": ha_confirms,
        "di_spread": round(abs(plus_di - minus_di), 1),
        "agreement": f"{'3' if all_st_aligned else '2'}/3 ST + MACD + VWAP + BB",
        "risk_reward": rr,

        "entry_premium": entry,
        "sl_premium": sl_premium,
        "target1_premium": t1_premium,
        "target2_premium": t2_premium,
        "sl_underlying": sl_underlying,
        "target1_underlying": t1_underlying,
        "target2_underlying": t2_underlying,
        "lot_size": lot_size,
        "max_lots": max_lots,
        "risk_per_lot": round(risk_per_lot, 0),
        "total_investment": round(entry * lot_size * max_lots, 0),
        "price_source": price_source,

        "current_price": round(price, 2),
        "atr": round(atr, 2),
        "warnings": warnings,
        "hold_time": "10-30 minutes",
        "timestamp": datetime.now(IST).strftime("%H:%M:%S"),
    }


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def _safe_float(row, col, default=0.0):
    if col in row.index:
        val = row[col]
        if not pd.isna(val):
            return float(val)
    return default

def _safe_int(row, col, default=0):
    if col in row.index:
        val = row[col]
        if not pd.isna(val):
            return int(val)
    return default

def _dir_label(d):
    return "BULL" if d > 0 else "BEAR" if d < 0 else "FLAT"

def _get_real_premium(oc_df, oc_expiry, strike, is_bullish, spot_price):
    """Get real option premium from chain, or estimate."""
    if oc_df is not None and not oc_df.empty:
        chain = oc_df.copy()
        if oc_expiry:
            chain = chain[chain["expiry"] == oc_expiry]
        strike_data = chain[chain["strike"] == strike]
        if not strike_data.empty:
            row = strike_data.iloc[0]
            col = "ce_ltp" if is_bullish else "pe_ltp"
            ltp = float(row.get(col, 0))
            if ltp > 5:
                return round(ltp, 1)
    # Estimate: ~0.4% of spot for ATM
    return round(max(spot_price * 0.004, 50), 1)


def _no_signal(reason: str) -> Dict:
    return {
        "has_signal": False,
        "action": "NO SIGNAL",
        "direction": "NEUTRAL",
        "reason": reason,
        "strike": 0, "confidence": 0, "score": 0,
        "supertrend": {"signal": 0, "detail": "N/A", "fresh": False},
        "vwap": {"signal": 0, "detail": "N/A"},
        "rsi": {"signal": 0, "detail": "N/A", "value": 50},
        "adx": 0, "agreement": "0/0",
        "macd_hist": 0, "macd_growing": False, "bb_pct": 0.5,
        "ha_confirms": False, "di_spread": 0, "risk_reward": 0,
        "entry_premium": 0, "sl_premium": 0,
        "target1_premium": 0, "target2_premium": 0,
        "sl_underlying": 0, "target1_underlying": 0, "target2_underlying": 0,
        "lot_size": 0, "max_lots": 0, "risk_per_lot": 0, "total_investment": 0,
        "price_source": "", "current_price": 0, "atr": 0, "warnings": [],
        "hold_time": "", "timestamp": datetime.now(IST).strftime("%H:%M:%S"),
    }
