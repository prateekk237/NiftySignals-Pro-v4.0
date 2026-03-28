"""
Signal Logger — Auto-logs every signal for accuracy tracking.
Checks outcomes at 30min and 60min after signal.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Optional, List
import pytz

from core.database import SessionLocal
from models import SignalLog

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def log_signal(
    signal_type: str,
    symbol: str,
    action: str,
    strike: int = 0,
    entry_premium: float = 0,
    confidence: float = 0,
    confluence_score: float = 0,
    adx: float = 0,
    vix: float = 0,
    is_expiry: bool = False,
) -> Optional[int]:
    """Log a signal for later accuracy tracking. Returns signal_log ID."""
    if action in ["NO TRADE", "NO SIGNAL"]:
        return None  # Don't track no-signals

    now = datetime.now(IST)
    db = SessionLocal()
    try:
        log = SignalLog(
            timestamp=now.isoformat(),
            signal_type=signal_type,
            symbol=symbol,
            action=action,
            strike=strike,
            entry_premium=entry_premium,
            confidence=confidence,
            confluence_score=confluence_score,
            outcome="PENDING",
            is_expiry_day=1 if is_expiry else 0,
            adx_at_signal=adx,
            vix_at_signal=vix,
            time_of_day=now.strftime("%H:%M"),
            weekday=now.strftime("%a"),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        logger.info(f"Signal logged: #{log.id} {signal_type} {symbol} {action} conf={confidence}")
        return log.id
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to log signal: {e}")
        return None
    finally:
        db.close()


def update_signal_outcome(
    log_id: int,
    current_premium: float,
    minutes_elapsed: int,
):
    """Update a signal's outcome after 30 or 60 minutes."""
    db = SessionLocal()
    try:
        log = db.query(SignalLog).filter(SignalLog.id == log_id).first()
        if not log or not log.entry_premium:
            return

        pnl_pct = ((current_premium - log.entry_premium) / log.entry_premium) * 100

        # Adjust for direction: BUY PE profits when premium goes up too
        # (we track the premium directly, not the underlying)

        if minutes_elapsed <= 35:
            log.premium_30m = current_premium
            log.pnl_30m_pct = round(pnl_pct, 1)
        elif minutes_elapsed <= 65:
            log.premium_60m = current_premium
            log.pnl_60m_pct = round(pnl_pct, 1)

        # Track max favorable/adverse
        if pnl_pct > 0:
            if log.max_favorable is None or pnl_pct > log.max_favorable:
                log.max_favorable = round(pnl_pct, 1)
        else:
            if log.max_adverse is None or pnl_pct < (log.max_adverse or 0):
                log.max_adverse = round(pnl_pct, 1)

        # Final outcome at 60 min
        if log.premium_60m is not None and log.outcome == "PENDING":
            if log.pnl_60m_pct >= 10:
                log.outcome = "WIN"
            elif log.pnl_60m_pct <= -10:
                log.outcome = "LOSS"
            else:
                log.outcome = "SCRATCH"

        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to update signal outcome: {e}")
    finally:
        db.close()


def get_accuracy_stats(days: int = 7, symbol: str = None) -> Dict:
    """Get signal accuracy statistics for the last N days."""
    db = SessionLocal()
    try:
        q = db.query(SignalLog).filter(SignalLog.outcome != "PENDING")
        if symbol:
            q = q.filter(SignalLog.symbol == symbol)

        logs = q.order_by(SignalLog.id.desc()).limit(200).all()
        if not logs:
            return {"total": 0, "message": "No completed signals yet"}

        total = len(logs)
        wins = sum(1 for l in logs if l.outcome == "WIN")
        losses = sum(1 for l in logs if l.outcome == "LOSS")
        scratches = sum(1 for l in logs if l.outcome == "SCRATCH")
        win_rate = (wins / total * 100) if total > 0 else 0

        # By signal type
        by_type = {}
        for st in ["CONFLUENCE", "QUICK", "BTST"]:
            subset = [l for l in logs if l.signal_type == st]
            if subset:
                st_wins = sum(1 for l in subset if l.outcome == "WIN")
                by_type[st] = {
                    "total": len(subset),
                    "wins": st_wins,
                    "win_rate": round(st_wins / len(subset) * 100, 1),
                    "avg_pnl_30m": round(sum(l.pnl_30m_pct or 0 for l in subset) / len(subset), 1),
                }

        # By time of day
        by_hour = {}
        for l in logs:
            if l.time_of_day:
                hour = l.time_of_day[:2]
                if hour not in by_hour:
                    by_hour[hour] = {"total": 0, "wins": 0}
                by_hour[hour]["total"] += 1
                if l.outcome == "WIN":
                    by_hour[hour]["wins"] += 1

        # Avg max favorable vs adverse
        avg_fav = sum(l.max_favorable or 0 for l in logs if l.max_favorable) / max(1, sum(1 for l in logs if l.max_favorable))
        avg_adv = sum(l.max_adverse or 0 for l in logs if l.max_adverse) / max(1, sum(1 for l in logs if l.max_adverse))

        # Expiry day performance
        expiry_logs = [l for l in logs if l.is_expiry_day]
        expiry_wins = sum(1 for l in expiry_logs if l.outcome == "WIN") if expiry_logs else 0

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "scratches": scratches,
            "win_rate": round(win_rate, 1),
            "by_signal_type": by_type,
            "by_hour": by_hour,
            "avg_max_favorable_pct": round(avg_fav, 1),
            "avg_max_adverse_pct": round(avg_adv, 1),
            "expiry_day_total": len(expiry_logs),
            "expiry_day_win_rate": round(expiry_wins / len(expiry_logs) * 100, 1) if expiry_logs else 0,
        }
    finally:
        db.close()


def get_recent_signals(limit: int = 20, symbol: str = None) -> List[Dict]:
    """Get recent signal logs for display."""
    db = SessionLocal()
    try:
        q = db.query(SignalLog)
        if symbol:
            q = q.filter(SignalLog.symbol == symbol)
        logs = q.order_by(SignalLog.id.desc()).limit(limit).all()
        return [{
            "id": l.id,
            "timestamp": l.timestamp,
            "signal_type": l.signal_type,
            "symbol": l.symbol,
            "action": l.action,
            "strike": l.strike,
            "entry_premium": l.entry_premium,
            "confidence": l.confidence,
            "pnl_30m_pct": l.pnl_30m_pct,
            "pnl_60m_pct": l.pnl_60m_pct,
            "outcome": l.outcome,
            "max_favorable": l.max_favorable,
            "max_adverse": l.max_adverse,
            "is_expiry_day": l.is_expiry_day,
            "time_of_day": l.time_of_day,
        } for l in logs]
    finally:
        db.close()
