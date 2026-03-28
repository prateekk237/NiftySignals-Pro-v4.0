"""
APScheduler Jobs — Independent background jobs per data type.
Each job: fetch → cache → WebSocket emit.
NEVER put all fetches in one job. NEVER make React trigger a fetch.
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

import pandas as pd
import pytz

from core.cache import cache
from core.config import settings, TIMEFRAMES, BTST_WEIGHTS, STRATEGY_WEIGHTS
from services.data_fetcher import data_fetcher
from services.indicator_service import indicator_service
from services.signal_service import signal_service
from services.btst_service import btst_service
from services.global_service import global_service
from services.sentiment_service import sentiment_service
from services.alert_service import alert_service
from services.quick_signal_service import quick_signal_service
from services.llm_service import llm_service
from ws import ws_emitter

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def _jitter(base_seconds: float, pct: float = 0.1) -> float:
    """Add small random jitter to prevent thundering herd."""
    return base_seconds + random.uniform(0, base_seconds * pct)


def _is_market_open() -> bool:
    return data_fetcher.is_market_open()


def _now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════════════════════════
#  JOB: Price Update — every 1 second
# ═══════════════════════════════════════════════════════════════

async def job_price_1s():
    """Fetch live spot price + VIX from NSE. Push via WebSocket."""
    if not _is_market_open():
        return

    try:
        for symbol in ["NIFTY50", "BANKNIFTY"]:
            nse_data = await data_fetcher.get_nse_live_price(symbol)
            if nse_data.get("price", 0) > 0:
                payload = {
                    "symbol": symbol,
                    "price": nse_data["price"],
                    "change": nse_data.get("change", 0),
                    "change_pct": nse_data.get("change_pct", 0),
                    "high": nse_data.get("high", 0),
                    "low": nse_data.get("low", 0),
                    "is_stale": False,
                    "timestamp": _now_ist(),
                }
                cache.set(f"price:{symbol}", payload, ttl=5)
                await ws_emitter.emit_price_update(payload, symbol)

        # VIX (comes from same NSE API)
        vix_data = await data_fetcher.get_nse_live_price("INDIAVIX")
        if vix_data.get("price", 0) > 0:
            vix_payload = {
                "vix": vix_data["price"],
                "vix_change": vix_data.get("change_pct", 0),
            }
            cache.set("vix:live", vix_payload, ttl=5)

    except Exception as e:
        logger.warning(f"job_price_1s failed: {e}")
        for symbol in ["NIFTY50", "BANKNIFTY"]:
            cached = cache.get(f"price:{symbol}")
            if cached:
                cached["is_stale"] = True
                await ws_emitter.emit_price_update(cached, symbol)


# ═══════════════════════════════════════════════════════════════
#  JOB: Option LTP Update — every 3 seconds
# ═══════════════════════════════════════════════════════════════

async def job_option_ltp_3s():
    """Fetch ATM option LTPs from NSE option chain."""
    if not _is_market_open():
        return

    try:
        for symbol in ["NIFTY50", "BANKNIFTY"]:
            nse_sym = "NIFTY" if symbol == "NIFTY50" else "BANKNIFTY"
            raw = await data_fetcher.fetch_option_chain(nse_sym)
            if not raw:
                continue

            oc_df, oc_meta = await data_fetcher.parse_option_chain(raw)
            if oc_df.empty:
                continue

            cache.set(f"option_chain:{symbol}", {"df": oc_df, "meta": oc_meta}, ttl=10)

            underlying = oc_meta.get("underlying_value", 0)
            expiries = oc_meta.get("expiry_dates", [])
            nearest_exp = expiries[0] if expiries else ""
            step = 50 if symbol == "NIFTY50" else 100
            atm = data_fetcher.get_atm_strike(underlying, step)

            # Find ATM row
            atm_row = oc_df[
                (oc_df["strike"] == atm) &
                (oc_df["expiry"] == nearest_exp)
            ]
            if atm_row.empty:
                continue

            row = atm_row.iloc[0]
            pcr_data = data_fetcher.calculate_pcr(oc_df, nearest_exp)

            payload = {
                "symbol": symbol,
                "atm_strike": atm,
                "atm_ce_ltp": float(row.get("ce_ltp", 0)),
                "atm_pe_ltp": float(row.get("pe_ltp", 0)),
                "expiry": nearest_exp,
                "pcr": pcr_data.get("pcr_oi", 0),
                "timestamp": _now_ist(),
            }
            cache.set(f"option_ltp:{symbol}", payload, ttl=10)
            await ws_emitter.emit_option_ltp_update(payload)

    except Exception as e:
        logger.warning(f"job_option_ltp_3s failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: OI Update — every 15 seconds
# ═══════════════════════════════════════════════════════════════

async def job_oi_15s():
    """Compute OI analysis from cached option chain data."""
    if not _is_market_open():
        return

    try:
        for symbol in ["NIFTY50", "BANKNIFTY"]:
            oc_cache = cache.get(f"option_chain:{symbol}")
            if not oc_cache:
                continue

            oc_df = oc_cache["df"]
            oc_meta = oc_cache["meta"]
            underlying = oc_meta.get("underlying_value", 0)
            expiries = oc_meta.get("expiry_dates", [])
            nearest_exp = expiries[0] if expiries else ""

            pcr_data = data_fetcher.calculate_pcr(oc_df, nearest_exp)
            max_pain = data_fetcher.calculate_max_pain(oc_df, nearest_exp)
            oi_sr = data_fetcher.get_oi_support_resistance(oc_df, underlying, nearest_exp)
            oi_bias = data_fetcher.analyze_oi_buildup(oc_df, underlying, nearest_exp)

            # Build OI data for chart
            step = 50 if symbol == "NIFTY50" else 100
            atm = data_fetcher.get_atm_strike(underlying, step)
            filtered = oc_df[
                (oc_df["expiry"] == nearest_exp) &
                (oc_df["strike"] >= atm - 10 * step) &
                (oc_df["strike"] <= atm + 10 * step)
            ]
            oi_data = filtered[["strike", "ce_oi", "pe_oi", "ce_chg_oi", "pe_chg_oi"]].to_dict("records") if not filtered.empty else []

            payload = {
                "symbol": symbol,
                "pcr": pcr_data.get("pcr_oi", 0),
                "max_pain": max_pain,
                "oi_bias": oi_bias,
                "support": oi_sr.get("support", []),
                "resistance": oi_sr.get("resistance", []),
                "oi_data": oi_data,
                "timestamp": _now_ist(),
            }
            cache.set(f"oi:{symbol}", payload, ttl=30)
            await ws_emitter.emit_oi_update(payload)

    except Exception as e:
        logger.warning(f"job_oi_15s failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: Quick Signal — every 15 seconds
# ═══════════════════════════════════════════════════════════════

async def job_quick_signal_15s():
    """Generate 5-min scalping signals."""
    if not _is_market_open():
        return

    try:
        for symbol in ["NIFTY50", "BANKNIFTY"]:
            df = await data_fetcher.fetch_fast_5min(symbol)
            if df.empty or len(df) < 15:
                continue

            df = indicator_service.compute_indicators(df, "Scalping")

            oc_cache = cache.get(f"option_chain:{symbol}")
            oc_df = oc_cache["df"] if oc_cache else None
            nearest_exp = ""
            if oc_cache:
                nearest_exp = oc_cache["meta"].get("expiry_dates", [""])[0]

            qs = quick_signal_service.generate(df, symbol, 10000, oc_df, nearest_exp)

            cache.set(f"quick_signal:{symbol}", qs, ttl=30)
            await ws_emitter.emit_quick_signal_update({**qs, "symbol": symbol})

    except Exception as e:
        logger.warning(f"job_quick_signal_15s failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: Alert Update — every 15 seconds
# ═══════════════════════════════════════════════════════════════

async def job_alerts_15s():
    """Generate real-time exit alerts."""
    if not _is_market_open():
        return

    try:
        for symbol in ["NIFTY50", "BANKNIFTY"]:
            # Get cached data
            price_data = cache.get(f"price:{symbol}")
            if not price_data:
                continue

            # We need OHLCV for indicators — get from signal job cache
            df_cache = cache.get(f"ohlcv:{symbol}")
            if df_cache is None:
                continue
            df = df_cache

            vix_live = cache.get("vix:live") or {}
            vix_current = vix_live.get("vix", 15.0)
            vix_prev = cache.get("vix:prev_close") or vix_current

            oi_data = cache.get(f"oi:{symbol}") or {}
            cpr_data = cache.get(f"cpr:{symbol}") or {}
            news_cache = cache.get("news:headlines") or []

            alerts = alert_service.generate_alerts(
                current_position="NONE",  # Server doesn't track user position
                df=df,
                vix_current=vix_current,
                vix_prev=vix_prev,
                pcr_current=oi_data.get("pcr", 0),
                news_headlines=news_cache,
                cpr_levels=cpr_data,
                oi_support=oi_data.get("support", []),
                oi_resistance=oi_data.get("resistance", []),
            )

            exit_rec = alert_service.get_exit_recommendation(
                alerts, "NONE", 0, price_data.get("price", 0)
            )

            payload = {
                "symbol": symbol,
                "alerts": alerts[:6],
                "exit_recommendation": exit_rec,
                "timestamp": _now_ist(),
            }
            cache.set(f"alerts:{symbol}", payload, ttl=30)
            await ws_emitter.emit_alert_update(payload)

    except Exception as e:
        logger.warning(f"job_alerts_15s failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: BTST Position Monitor — every 3 seconds
#  Now with: Trailing SL, Partial Exits, Telegram Alerts
# ═══════════════════════════════════════════════════════════════

async def job_position_monitor_3s():
    """Monitor open BTST positions with trailing SL and partial exits."""
    if not _is_market_open():
        return

    try:
        from core.database import SessionLocal
        from models import BTSTPosition
        from services.trade_manager import compute_trailing_sl, calculate_partial_exit
        from services.telegram_service import telegram
        import json

        db = SessionLocal()
        try:
            open_positions = db.query(BTSTPosition).filter(
                BTSTPosition.status == "OPEN"
            ).all()

            for pos in open_positions:
                oc_cache = cache.get(f"option_chain:{pos.symbol}")
                if not oc_cache:
                    continue

                oc_df = oc_cache["df"]
                nearest_exp = oc_cache["meta"].get("expiry_dates", [""])[0]
                strike_row = oc_df[
                    (oc_df["strike"] == pos.strike_price) &
                    (oc_df["expiry"] == nearest_exp)
                ]
                if strike_row.empty:
                    continue

                row = strike_row.iloc[0]
                ltp_col = "ce_ltp" if pos.option_type == "CE" else "pe_ltp"
                current_ltp = float(row.get(ltp_col, 0))
                if current_ltp <= 0:
                    continue

                # ── Trailing SL computation ───────────────────
                trail_result = compute_trailing_sl(
                    entry_premium=pos.entry_premium,
                    current_ltp=current_ltp,
                    highest_ltp=pos.highest_ltp or pos.entry_premium,
                    current_trail_stage=pos.trail_stage or "ENTRY",
                    symbol=pos.symbol,
                )

                # Update position in DB
                pos.trailing_sl = trail_result["trailing_sl"]
                pos.highest_ltp = trail_result["highest_ltp"]
                pos.trail_stage = trail_result["trail_stage"]

                # Stage change alert
                if trail_result["stage_changed"]:
                    logger.info(
                        f"Position #{pos.id} trail stage → {trail_result['trail_stage']} "
                        f"SL=₹{trail_result['trailing_sl']} peak={trail_result['peak_pnl_pct']}%"
                    )
                    if telegram.is_configured:
                        await telegram.alert_trailing_sl(
                            pos.id, pos.symbol, trail_result["trail_stage"],
                            trail_result["trailing_sl"], trail_result["current_pnl_pct"],
                        )

                # ── Partial Exit Check ────────────────────────
                partial = calculate_partial_exit(
                    total_lots=pos.total_lots,
                    exited_lots=pos.exited_lots,
                    current_pnl_pct=trail_result["current_pnl_pct"],
                    trail_stage=trail_result["trail_stage"],
                )
                if partial:
                    # Record partial exit
                    exits = json.loads(pos.partial_exits or "[]")
                    exits.append({
                        "lots": partial["lots_to_exit"],
                        "premium": current_ltp,
                        "pnl_pct": trail_result["current_pnl_pct"],
                        "type": partial["exit_type"],
                        "time": _now_ist(),
                    })
                    pos.partial_exits = json.dumps(exits)
                    pos.exited_lots += partial["lots_to_exit"]

                    await ws_emitter.emit_btst_target_alert({
                        "position_id": pos.id, "symbol": pos.symbol,
                        "option_type": pos.option_type,
                        "entry_premium": pos.entry_premium,
                        "current_ltp": current_ltp,
                        "pnl_pct": trail_result["current_pnl_pct"],
                        "message": partial["reason"],
                        "exit_type": partial["exit_type"],
                        "lots_exited": partial["lots_to_exit"],
                        "remaining_lots": partial["remaining_after"],
                        "timestamp": _now_ist(),
                    })

                    if telegram.is_configured:
                        await telegram.alert_exit(
                            pos.id, pos.symbol, partial["exit_type"],
                            trail_result["current_pnl_pct"], current_ltp,
                        )

                # ── SL Hit Check (trailing or initial) ────────
                if trail_result["should_exit"]:
                    pnl_pct = trail_result["current_pnl_pct"]
                    alert_type = trail_result["alert_type"]

                    await ws_emitter.emit_btst_sl_alert({
                        "position_id": pos.id, "symbol": pos.symbol,
                        "option_type": pos.option_type,
                        "entry_premium": pos.entry_premium,
                        "current_ltp": current_ltp,
                        "pnl_pct": round(pnl_pct, 1),
                        "trail_stage": trail_result["trail_stage"],
                        "message": f"{alert_type} — Exit now. SL ₹{trail_result['trailing_sl']}",
                        "timestamp": _now_ist(),
                    })

                    if telegram.is_configured:
                        await telegram.alert_exit(
                            pos.id, pos.symbol, alert_type, pnl_pct, current_ltp,
                        )

                db.commit()

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"job_position_monitor_3s failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: Main Signal — every 60 seconds
# ═══════════════════════════════════════════════════════════════

async def job_signal_60s():
    """Full confluence signal computation. The heaviest job."""
    try:
        for symbol in ["NIFTY50", "BANKNIFTY"]:
            tf_key = "Intraday"
            tf = TIMEFRAMES[tf_key]

            # Fetch OHLCV
            df = await data_fetcher.fetch_ohlcv(symbol, tf["interval"], tf["period"])
            if df.empty:
                continue

            # Compute all indicators
            df = indicator_service.compute_indicators(df, tf_key)
            cache.set(f"ohlcv:{symbol}", df, ttl=120)

            current_price = float(df["Close"].iloc[-1])
            indicator_signals = indicator_service.get_signals(df)
            cache.set(f"indicator_signals:{symbol}", indicator_signals, ttl=120)

            # CPR
            prev_ohlc = await data_fetcher.get_previous_day_ohlc(symbol)
            if prev_ohlc["high"] > 0:
                cpr = indicator_service.calc_cpr(prev_ohlc["high"], prev_ohlc["low"], prev_ohlc["close"])
                cache.set(f"cpr:{symbol}", cpr, ttl=86400)

            # ORB
            orb = indicator_service.calc_orb_levels(df)
            cache.set(f"orb:{symbol}", orb, ttl=86400)

            # Get cached global/vix/oi/news
            global_data = cache.get("global:score") or {"score": 0, "label": "N/A"}
            vix_live = cache.get("vix:live") or {}
            vix_val = vix_live.get("vix", 15.0)
            vix_analysis = cache.get("vix:analysis") or {"signal_score": 0}
            oi_data = cache.get(f"oi:{symbol}") or {}
            news_data = cache.get("news:score") or {"score": 0}

            pcr_data = {"pcr_oi": oi_data.get("pcr", 0)}
            oi_bias = oi_data.get("oi_bias", "NEUTRAL")

            # ── Expiry Day Intelligence ───────────────────────
            from services.trade_manager import is_expiry_day
            expiry_info = is_expiry_day(symbol)
            cache.set(f"expiry:{symbol}", expiry_info, ttl=3600)

            # Block new BUY signals on expiry day after 1:30 PM
            if expiry_info.get("block_new_buys"):
                payload = {
                    "symbol": symbol, "action": "NO TRADE",
                    "signal_label": "EXPIRY BLOCK",
                    "confluence_score": 0, "confidence": 0,
                    "strike": 0, "entry_premium": 0, "sl_premium": 0,
                    "target1_premium": 0, "target2_premium": 0,
                    "components": {}, "trade": {"action": "NO TRADE", "reasoning": [expiry_info["reason"]]},
                    "timestamp": _now_ist(), "expiry_info": expiry_info,
                }
                cache.set(f"signal:{symbol}", payload, ttl=120)
                await ws_emitter.emit_signal_update(payload)
                continue

            # Confluence
            score, label, components = signal_service.calculate_confluence(
                indicator_signals=indicator_signals,
                pcr_data=pcr_data,
                oi_bias=oi_bias,
                news_score=news_data.get("score", 0),
                vix_level=vix_val,
                global_score=global_data.get("score", 0),
                vix_signal_score=vix_analysis.get("signal_score", 0),
            )

            # Get option chain for trade recommendation
            oc_cache = cache.get(f"option_chain:{symbol}")
            oc_df = oc_cache["df"] if oc_cache else None

            trade = signal_service.generate_trade(
                symbol=symbol,
                current_price=current_price,
                confluence_score=score,
                signal_label=label,
                df=df,
                oc_df=oc_df,
                vix_level=vix_val,
                capital=10000,
                timeframe=tf_key,
            )

            # ── Expiry Day Adjustments ────────────────────────
            if expiry_info.get("tighten_targets") and trade["action"] != "NO TRADE":
                mult = expiry_info.get("target_multiplier", 0.6)
                trade["target1_premium"] = round(
                    trade["entry_premium"] + (trade["target1_premium"] - trade["entry_premium"]) * mult, 1
                )
                trade["reasoning"] = trade.get("reasoning", []) + [
                    f"Expiry day — targets tightened to {mult*100:.0f}%"
                ]
            if expiry_info.get("sl_tighter") and trade["action"] != "NO TRADE":
                sl_mult = expiry_info.get("sl_multiplier", 0.8)
                sl_diff = trade["entry_premium"] - trade["sl_premium"]
                trade["sl_premium"] = round(trade["entry_premium"] - sl_diff * sl_mult, 1)

            payload = {
                "symbol": symbol,
                "action": trade["action"],
                "signal_label": label,
                "confluence_score": score,
                "confidence": trade["confidence"],
                "strike": trade["strike"],
                "entry_premium": trade["entry_premium"],
                "sl_premium": trade["sl_premium"],
                "target1_premium": trade["target1_premium"],
                "target2_premium": trade["target2_premium"],
                "components": components,
                "trade": trade,
                "timestamp": _now_ist(),
                "expiry_info": expiry_info,
            }
            cache.set(f"signal:{symbol}", payload, ttl=120)
            await ws_emitter.emit_signal_update(payload)

            # ── Auto-log signal for accuracy tracking ─────────
            from services.signal_logger import log_signal
            from services.telegram_service import telegram

            adx_sig = indicator_signals.get("adx", {})
            log_signal(
                signal_type="CONFLUENCE",
                symbol=symbol, action=trade["action"],
                strike=trade["strike"], entry_premium=trade["entry_premium"],
                confidence=trade["confidence"], confluence_score=score,
                adx=adx_sig.get("value", 0) if isinstance(adx_sig, dict) else 0,
                vix=vix_val,
                is_expiry=expiry_info.get("is_expiry_day", False),
            )

            # ── Telegram alert for actionable signals ─────────
            if trade["action"] != "NO TRADE" and telegram.is_configured:
                await telegram.alert_signal("CONFLUENCE", symbol, {
                    **trade, "confluence_score": score,
                })

    except Exception as e:
        logger.warning(f"job_signal_60s failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: VIX Analysis — every 60 seconds
# ═══════════════════════════════════════════════════════════════

async def job_vix_analysis_60s():
    """Analyze India VIX zone, trend, and strategy."""
    try:
        vix_live = cache.get("vix:live") or {}
        vix_val = vix_live.get("vix", 0)
        if vix_val <= 0:
            return

        vix_hist_cache = cache.get("vix:history")
        vix_hist = vix_hist_cache if vix_hist_cache is not None else pd.DataFrame()

        analysis = global_service.analyze_india_vix(vix_val, vix_hist)
        cache.set("vix:analysis", analysis, ttl=120)
        await ws_emitter.emit_vix_analysis_update({
            "vix": vix_val,
            **analysis,
            "timestamp": _now_ist(),
        })

    except Exception as e:
        logger.warning(f"job_vix_analysis_60s failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: News Sentiment — every 3 minutes
# ═══════════════════════════════════════════════════════════════

async def job_sentiment_3m():
    """Fetch news and compute sentiment."""
    try:
        nim_client = llm_service.get_client() if settings.enable_llm else None
        score, label, headlines = await sentiment_service.calculate_sentiment(nim_client)

        cache.set("news:score", {"score": score, "label": label}, ttl=300)
        cache.set("news:headlines", headlines, ttl=300)

        await ws_emitter.emit_news_update({
            "score": score,
            "label": label,
            "headlines": headlines[:10],
            "timestamp": _now_ist(),
        })

    except Exception as e:
        logger.warning(f"job_sentiment_3m failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: Global Markets — every 5 minutes
# ═══════════════════════════════════════════════════════════════

async def job_global_5m():
    """Fetch global market data and compute score."""
    try:
        global_data = await global_service.fetch_all_global_data()
        if not global_data:
            return

        score, label, details = global_service.calculate_global_score(global_data)
        cache.set("global:data", global_data, ttl=600)
        cache.set("global:score", {"score": score, "label": label, "details": details}, ttl=600)

        # Indian indices
        indian_idx = await global_service.analyze_indian_indices()
        cache.set("global:indian_indices", indian_idx, ttl=600)

        await ws_emitter.emit_global_update({
            "score": score,
            "label": label,
            "details": details,
            "indian_indices": indian_idx,
            "timestamp": _now_ist(),
        })

    except Exception as e:
        logger.warning(f"job_global_5m failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: BTST Prediction — every 5 minutes
#  NOTE: No market hours guard — BTST must run during closing session
#  and even after market close for overnight prediction accuracy.
# ═══════════════════════════════════════════════════════════════

async def job_btst_5m():
    """Compute BTST gap prediction using ALL available cached data (10 factors)."""
    try:
        global_data = cache.get("global:data") or {}

        vix_live = cache.get("vix:live") or {}
        vix_current = vix_live.get("vix", 15.0)
        vix_prev = cache.get("vix:prev_close") or vix_current

        # News data for BTST
        news_data = cache.get("news:score") or {}
        news_score = news_data.get("score", 0)
        news_headlines = cache.get("news:headlines") or []

        for symbol in ["NIFTY50", "BANKNIFTY"]:
            df = cache.get(f"ohlcv:{symbol}")
            if df is None:
                continue

            indicator_signals = cache.get(f"indicator_signals:{symbol}") or {}
            oi_data = cache.get(f"oi:{symbol}") or {}

            btst = btst_service.predict_gap(
                global_data=global_data,
                vix_current=vix_current,
                vix_prev_close=vix_prev,
                df_today=df,
                pcr_eod=oi_data.get("pcr", 0),
                indicator_signals=indicator_signals,
                news_score=news_score,
                news_headlines=news_headlines,
            )

            cache.set(f"btst:{symbol}", btst, ttl=600)
            await ws_emitter.emit_btst_update({**btst, "symbol": symbol})

    except Exception as e:
        logger.warning(f"job_btst_5m failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: VIX History — every 10 minutes
# ═══════════════════════════════════════════════════════════════

async def job_vix_history_10m():
    """Fetch VIX history for chart and analysis."""
    try:
        vix_all = await data_fetcher.get_vix_all()
        cache.set("vix:live", {"vix": vix_all["current"], "vix_change": 0}, ttl=30)
        cache.set("vix:prev_close", vix_all["prev_close"], ttl=86400)

        if not vix_all["history"].empty:
            hist = vix_all["history"]
            cache.set("vix:history", hist, ttl=900)

            chart_data = [
                {"date": str(idx.date()), "close": round(float(row["Close"]), 2)}
                for idx, row in hist.tail(60).iterrows()
            ]
            await ws_emitter.emit_vix_history_update({
                "chart_data": chart_data,
                "current": vix_all["current"],
                "prev_close": vix_all["prev_close"],
                "timestamp": _now_ist(),
            })

    except Exception as e:
        logger.warning(f"job_vix_history_10m failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  JOB: Daily Levels — once at 9:15 AM
# ═══════════════════════════════════════════════════════════════

async def job_daily_levels():
    """Compute CPR + ORB levels at market open."""
    try:
        for symbol in ["NIFTY50", "BANKNIFTY"]:
            prev_ohlc = await data_fetcher.get_previous_day_ohlc(symbol)
            if prev_ohlc["high"] > 0:
                cpr = indicator_service.calc_cpr(
                    prev_ohlc["high"], prev_ohlc["low"], prev_ohlc["close"]
                )
                cache.set(f"cpr:{symbol}", cpr, ttl=86400)

                await ws_emitter.emit_levels_update({
                    "symbol": symbol,
                    "cpr": cpr,
                    "timestamp": _now_ist(),
                })

    except Exception as e:
        logger.warning(f"job_daily_levels failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  SCHEDULER SETUP
# ═══════════════════════════════════════════════════════════════

def setup_scheduler(scheduler):
    """Register all jobs with APScheduler. Called from main.py startup."""

    # Helper to wrap async jobs for APScheduler's sync thread pool
    def _run_async(coro_func):
        def wrapper():
            try:
                asyncio.run(coro_func())
            except Exception as e:
                logger.error(f"Scheduler job error: {e}")
        return wrapper

    # ── Market Hours Jobs ─────────────────────────────────────
    scheduler.add_job(_run_async(job_price_1s), "interval", seconds=1,
                      id="job_price_1s", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_option_ltp_3s), "interval", seconds=3,
                      id="job_option_ltp_3s", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_position_monitor_3s), "interval", seconds=3,
                      id="job_position_monitor_3s", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_oi_15s), "interval", seconds=15,
                      id="job_oi_15s", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_quick_signal_15s), "interval", seconds=15,
                      id="job_quick_signal_15s", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_alerts_15s), "interval", seconds=15,
                      id="job_alerts_15s", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_signal_60s), "interval", seconds=60,
                      id="job_signal_60s", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_vix_analysis_60s), "interval", seconds=60,
                      id="job_vix_analysis_60s", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_sentiment_3m), "interval", seconds=180,
                      id="job_sentiment_3m", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_global_5m), "interval", seconds=300,
                      id="job_global_5m", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_btst_5m), "interval", seconds=300,
                      id="job_btst_5m", max_instances=1, replace_existing=True)

    scheduler.add_job(_run_async(job_vix_history_10m), "interval", seconds=600,
                      id="job_vix_history_10m", max_instances=1, replace_existing=True)

    # ── Daily Jobs ────────────────────────────────────────────
    scheduler.add_job(_run_async(job_daily_levels), "cron",
                      hour=9, minute=15, timezone=IST,
                      id="job_daily_levels", max_instances=1, replace_existing=True)

    logger.info("All scheduler jobs registered")
