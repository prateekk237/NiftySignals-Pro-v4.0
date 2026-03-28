"""
╔══════════════════════════════════════════════════════════════╗
║  SIGNAL ENGINE v3.0 — Fixed: No more permanent NO TRADE     ║
║                                                              ║
║  ROOT CAUSE FIXES:                                           ║
║  1. Zero-dilution: Missing components excluded from avg     ║
║  2. Weight normalization: Divide by PRESENT weight only     ║
║  3. Thresholds lowered: BUY at 0.15 (was 0.25)             ║
║  4. Kill switch removed: abs<0.10 was double-blocking       ║
║  5. VIX dampening softened: max 0.92x (was 0.85x)          ║
║  6. ST+RSI combo improved: stronger signal extraction       ║
║  7. Confidence scale recalibrated to new thresholds         ║
╚══════════════════════════════════════════════════════════════╝
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pytz

from config import (
    NIFTY_LOT_SIZE, BANKNIFTY_LOT_SIZE,
    STRIKE_STEP_NIFTY, STRIKE_STEP_BANKNIFTY,
    PCR_EXTREME_BULLISH, PCR_BULLISH, PCR_BEARISH, PCR_EXTREME_BEARISH,
    VIX_LOW, VIX_NORMAL_HIGH, VIX_HIGH,
    SL_OPTION_BUY_PCT, SL_ATR_MULTIPLIER, RISK_REWARD_MIN,
    MAX_RISK_PER_TRADE_PCT, DEFAULT_CAPITAL,
    STRATEGY_WEIGHTS,
)
from indicators import get_indicator_signals, calc_cpr, calc_orb_levels
from data_fetcher import get_atm_strike, get_previous_day_ohlc, is_market_open, get_market_session

IST = pytz.timezone("Asia/Kolkata")

# ═══════════════════════════════════════════════════════════════
#  v3 THRESHOLDS — calibrated to actually trigger
# ═══════════════════════════════════════════════════════════════
STRONG_BUY_THRESHOLD = 0.35   # Was 0.45 — unreachable with missing data
BUY_THRESHOLD = 0.15          # Was 0.25 — zero-dilution made this impossible
NEUTRAL_LOW = -0.15           # Was -0.25 — symmetric with BUY
STRONG_SELL_THRESHOLD = -0.35 # Was -0.45


def calculate_confluence_score(
    indicator_signals: Dict[str, dict],
    pcr_data: Optional[dict] = None,
    oi_bias: str = "NEUTRAL",
    news_score: float = 0.0,
    vix_level: float = 0.0,
    global_score: float = 0.0,
    vix_signal_score: float = 0.0,
) -> Tuple[float, str, Dict[str, float]]:
    """
    Calculate weighted confluence score from ALL available signal sources.

    v3 FIX: Only count components that have actual data.
    Missing data (global, news, VIX, OI) no longer dilutes the score.
    """
    components = {}

    # ── Technical Indicators ─────────────────────────────────

    # Supertrend + RSI combo (FIXED: better extraction)
    st_fast = indicator_signals.get("supertrend_fast", {}).get("signal", 0)
    st_med = indicator_signals.get("supertrend_med", {}).get("signal", 0)
    rsi_7 = indicator_signals.get("rsi_7", {}).get("signal", 0)

    if st_fast != 0:
        if rsi_7 != 0:
            # Both present: combine with agreement bonus
            if (st_fast > 0 and rsi_7 > 0) or (st_fast < 0 and rsi_7 < 0):
                # AGREE — strong signal, boost
                combo = (st_fast * 0.6 + rsi_7 * 0.4) * 1.2
            else:
                # DISAGREE — use the stronger one at reduced strength
                combo = max(st_fast, rsi_7, key=abs) * 0.5
            components["supertrend_rsi"] = np.clip(combo, -1, 1)
        else:
            # Only Supertrend — still valuable at reduced weight
            components["supertrend_rsi"] = st_fast * 0.7

        # BONUS: Multi-Supertrend alignment
        if st_med != 0 and ((st_fast > 0 and st_med > 0) or (st_fast < 0 and st_med < 0)):
            # Both fast and medium agree — boost
            components["supertrend_rsi"] = np.clip(
                components["supertrend_rsi"] * 1.15, -1, 1
            )

    ema_sig = indicator_signals.get("ema_cross", {}).get("signal", 0)
    if ema_sig != 0:
        components["ema_crossover"] = ema_sig

    macd_sig = indicator_signals.get("macd", {}).get("signal", 0)
    if macd_sig != 0:
        components["macd"] = macd_sig

    vwap_sig = indicator_signals.get("vwap", {}).get("signal", 0)
    if vwap_sig != 0:
        components["vwap"] = vwap_sig

    bb_sig = indicator_signals.get("bollinger", {}).get("signal", 0)
    if bb_sig != 0:
        components["bollinger"] = bb_sig

    adx_sig = indicator_signals.get("adx", {}).get("signal", 0)
    if adx_sig != 0:
        components["adx_trend"] = adx_sig

    # ── PCR / OI ─────────────────────────────────────────────
    if pcr_data and pcr_data.get("pcr_oi", 0) > 0:
        pcr = pcr_data["pcr_oi"]
        if pcr >= PCR_EXTREME_BULLISH:
            pcr_sig = 0.7
        elif pcr >= PCR_BULLISH:
            pcr_sig = 0.3
        elif pcr <= PCR_EXTREME_BEARISH:
            pcr_sig = -0.7
        elif pcr <= PCR_BEARISH:
            pcr_sig = -0.3
        else:
            pcr_sig = 0.0
        if pcr_sig != 0:
            components["pcr_sentiment"] = pcr_sig

    if oi_bias != "NEUTRAL":
        oi_map = {"BULLISH": 0.6, "BEARISH": -0.6}
        components["oi_analysis"] = oi_map.get(oi_bias, 0.0)

    # ── News Sentiment (only if meaningful) ───────────────────
    if abs(news_score) > 0.05:
        components["news_sentiment"] = np.clip(news_score, -1, 1)

    # ── Global Market Score (only if data present) ────────────
    if abs(global_score) > 0.01:
        components["global_cues"] = np.clip(global_score, -1, 1)

    # ── VIX Analysis Score (only if meaningful) ───────────────
    if abs(vix_signal_score) > 0.01:
        components["vix_analysis"] = np.clip(vix_signal_score, -1, 1)

    # ═══════════════════════════════════════════════════════════
    #  v3 FIX: Divide by PRESENT weight only
    #  This is the critical fix. Old code divided by total_weight=1.0
    #  even when 5 components had no data (0 value, 43% weight).
    #  Now we only sum weights for components that actually exist.
    # ═══════════════════════════════════════════════════════════
    score = 0.0
    present_weight = 0.0

    for key, weight in STRATEGY_WEIGHTS.items():
        if key in components:
            score += components[key] * weight
            present_weight += weight

    # Normalize by present weight (not total)
    if present_weight > 0:
        score = score / present_weight
    score = np.clip(score, -1, 1)

    # ═══════════════════════════════════════════════════════════
    #  v3 FIX: Softer VIX dampening
    #  Old: VIX>25 → ×0.85, VIX>20 → ×0.92
    #  New: VIX>25 → ×0.92, VIX>20 → ×0.96 (reduce direction, don't kill)
    # ═══════════════════════════════════════════════════════════
    if vix_level > VIX_HIGH:
        score *= 0.92
    elif vix_level > VIX_NORMAL_HIGH:
        score *= 0.96

    # ═══════════════════════════════════════════════════════════
    #  v3 THRESHOLDS — lower to account for real-world data gaps
    # ═══════════════════════════════════════════════════════════
    if score >= STRONG_BUY_THRESHOLD:
        label = "STRONG BUY"
    elif score >= BUY_THRESHOLD:
        label = "BUY"
    elif score <= STRONG_SELL_THRESHOLD:
        label = "STRONG SELL"
    elif score <= NEUTRAL_LOW:
        label = "SELL"
    else:
        label = "NEUTRAL"

    return round(score, 3), label, components


def generate_trade_recommendation(
    symbol: str, current_price: float, confluence_score: float,
    signal_label: str, df: pd.DataFrame,
    oc_df: pd.DataFrame = None, vix_level: float = 15.0,
    capital: float = DEFAULT_CAPITAL, timeframe: str = "Intraday",
) -> Dict:
    """
    Generate complete actionable trade recommendation.

    v3 FIX: Removed the abs(score) < 0.10 kill switch.
    The threshold system already handles NEUTRAL — this was
    double-blocking and preventing signals from ever firing.
    """
    # v3: Only block on NEUTRAL label, not on abs(score) threshold
    if signal_label == "NEUTRAL":
        return _no_trade(
            f"Mixed signals — score {confluence_score:+.3f} "
            f"(need >{BUY_THRESHOLD:+.2f} for BUY or <{NEUTRAL_LOW:+.2f} for SELL)"
        )

    if "BANK" in symbol.upper():
        lot_size = BANKNIFTY_LOT_SIZE
        strike_step = STRIKE_STEP_BANKNIFTY
    else:
        lot_size = NIFTY_LOT_SIZE
        strike_step = STRIKE_STEP_NIFTY

    atm_strike = get_atm_strike(current_price, strike_step)
    is_bullish = confluence_score > 0

    # v3: Confidence calibrated to new thresholds
    # 0.15 → 33%, 0.25 → 55%, 0.35 → 78%, 0.50+ → 95%
    raw_conf = abs(confluence_score)
    if raw_conf >= 0.50:
        confidence = 95
    elif raw_conf >= STRONG_BUY_THRESHOLD:
        confidence = 75 + (raw_conf - STRONG_BUY_THRESHOLD) / (0.50 - STRONG_BUY_THRESHOLD) * 20
    elif raw_conf >= BUY_THRESHOLD:
        confidence = 33 + (raw_conf - BUY_THRESHOLD) / (STRONG_BUY_THRESHOLD - BUY_THRESHOLD) * 42
    else:
        confidence = raw_conf / BUY_THRESHOLD * 33
    confidence = min(confidence, 98)

    strategy_type = "BUY"
    if vix_level > VIX_HIGH and abs(confluence_score) < STRONG_BUY_THRESHOLD:
        strategy_type = "SELL"

    atr = float(df["ATR_14"].iloc[-1]) if "ATR_14" in df.columns and not pd.isna(df["ATR_14"].iloc[-1]) else current_price * 0.01

    if is_bullish:
        action = f"{strategy_type} CE"
        strike = atm_strike
        otm_strike = atm_strike + strike_step
        sl_underlying = current_price - atr * SL_ATR_MULTIPLIER
        target1_underlying = current_price + atr * 1.5
        target2_underlying = current_price + atr * 2.5
    else:
        action = f"{strategy_type} PE"
        strike = atm_strike
        otm_strike = atm_strike - strike_step
        sl_underlying = current_price + atr * SL_ATR_MULTIPLIER
        target1_underlying = current_price - atr * 1.5
        target2_underlying = current_price - atr * 2.5

    est_delta = 0.50 if strike == atm_strike else 0.35
    est_premium = max(atr * est_delta * 2.5, 50)

    actual_premium = None
    if oc_df is not None and not oc_df.empty:
        nearest = oc_df[oc_df["strike"] == strike]
        if not nearest.empty:
            row = nearest.iloc[0]
            col = "ce_ltp" if is_bullish else "pe_ltp"
            if row[col] > 0:
                actual_premium = float(row[col])

    entry = actual_premium if actual_premium else round(est_premium, 1)

    if strategy_type == "BUY":
        sl_prem = round(entry * (1 - SL_OPTION_BUY_PCT / 100), 1)
        t1_prem = round(entry * 1.5, 1)
        t2_prem = round(entry * 2.0, 1)
        risk_per_lot = (entry - sl_prem) * lot_size
    else:
        sl_prem = round(entry * 1.5, 1)
        t1_prem = round(entry * 0.5, 1)
        t2_prem = round(entry * 0.25, 1)
        risk_per_lot = (sl_prem - entry) * lot_size

    max_risk = capital * (MAX_RISK_PER_TRADE_PCT / 100)
    max_lots = max(1, int(max_risk / risk_per_lot)) if risk_per_lot > 0 else 1

    cost_per_lot = entry * lot_size
    if cost_per_lot > 0:
        affordable_lots = max(1, int((capital * 0.80) / cost_per_lot))
        max_lots = min(max_lots, affordable_lots)

    capital_warning = ""
    if cost_per_lot > capital:
        capital_warning = (
            f"⚠️ Capital ₹{capital:,} below 1-lot cost ₹{cost_per_lot:,.0f}."
        )

    reasons = []
    if abs(confluence_score) >= STRONG_BUY_THRESHOLD:
        reasons.append(f"Strong confluence ({confluence_score:+.3f})")
    else:
        reasons.append(f"Moderate confluence ({confluence_score:+.3f})")
    reasons.append(f"{'Bullish' if is_bullish else 'Bearish'} across multiple indicators")
    if vix_level < VIX_LOW:
        reasons.append(f"VIX low ({vix_level:.1f}) — premiums cheap")
    elif vix_level > VIX_HIGH:
        reasons.append(f"VIX elevated ({vix_level:.1f})")

    tf_advice = {
        "Scalping": "Quick scalp: Exit within 15-30 mins",
        "Intraday": "Must exit before 3:15 PM. Trail SL after T1",
        "Swing": "Hold 2-5 days. Daily close below SL = exit",
        "Positional": "Hold till weekly expiry. Weekly close for SL",
    }
    reasons.append(tf_advice.get(timeframe, ""))

    return {
        "action": action, "direction": "BULLISH" if is_bullish else "BEARISH",
        "strike": strike, "otm_strike": otm_strike,
        "entry_premium": entry, "sl_premium": sl_prem,
        "target1_premium": t1_prem, "target2_premium": t2_prem,
        "sl_underlying": round(sl_underlying, 2),
        "target1_underlying": round(target1_underlying, 2),
        "target2_underlying": round(target2_underlying, 2),
        "lot_size": lot_size, "max_lots": max_lots,
        "risk_per_lot": round(risk_per_lot, 0),
        "total_risk": round(risk_per_lot * max_lots, 0),
        "total_investment": round(entry * lot_size * max_lots, 0),
        "potential_profit_t1": round(abs(t1_prem - entry) * lot_size * max_lots, 0),
        "potential_profit_t2": round(abs(t2_prem - entry) * lot_size * max_lots, 0),
        "risk_reward": round(abs(t1_prem - entry) / max(abs(entry - sl_prem), 0.01), 2),
        "confidence": round(confidence, 0),
        "strategy_type": strategy_type, "reasoning": reasons,
        "atr": round(atr, 2), "timeframe": timeframe,
        "capital_warning": capital_warning,
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _no_trade(reason: str) -> Dict:
    return {
        "action": "NO TRADE", "direction": "NEUTRAL",
        "strike": 0, "otm_strike": 0,
        "entry_premium": 0, "sl_premium": 0,
        "target1_premium": 0, "target2_premium": 0,
        "sl_underlying": 0, "target1_underlying": 0, "target2_underlying": 0,
        "lot_size": 0, "max_lots": 0, "risk_per_lot": 0,
        "total_risk": 0, "total_investment": 0,
        "potential_profit_t1": 0, "potential_profit_t2": 0,
        "risk_reward": 0, "confidence": 0, "strategy_type": "NONE",
        "reasoning": [reason], "atr": 0, "timeframe": "",
        "capital_warning": "",
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
    }


def select_best_strategy(vix, pcr, adx, timeframe, is_expiry_day=False):
    strategies = []
    if is_expiry_day:
        strategies.append({"name": "Expiry Credit Spread", "type": "SELL", "win_rate": "65-70%",
                           "detail": "Sell OTM spreads; theta accelerates after 12 PM"})
    if vix < VIX_LOW:
        strategies.append({"name": "Directional Option Buying", "type": "BUY", "win_rate": "~65%",
                           "detail": "Low VIX = cheap premiums. Buy ATM with trend"})
    elif vix > VIX_HIGH:
        strategies.append({"name": "Short Strangle (hedged)", "type": "SELL", "win_rate": "68%",
                           "detail": "High VIX = rich premiums. Sell OTM CE+PE"})
    if timeframe == "Scalping":
        strategies.append({"name": "VWAP Bounce Scalp", "type": "BUY", "win_rate": "~78%",
                           "detail": "Buy CE/PE on VWAP bounce with volume"})
    elif timeframe == "Intraday":
        strategies.append({"name": "ORB + Supertrend", "type": "BUY", "win_rate": "~71%",
                           "detail": "ORB breakout confirmed by Supertrend"})
    elif timeframe == "Swing":
        strategies.append({"name": "EMA 9/21 + MACD", "type": "BUY", "win_rate": "~73%",
                           "detail": "Enter on EMA cross, confirm with MACD"})
    elif timeframe == "Positional":
        strategies.append({"name": "Triple Supertrend + 200 EMA", "type": "BUY", "win_rate": "~60%",
                           "detail": "All 3 Supertrends align + above 200 EMA"})
    if not strategies:
        strategies.append({"name": "Wait for Setup", "type": "NONE", "win_rate": "N/A",
                           "detail": "No clear edge"})
    return strategies
