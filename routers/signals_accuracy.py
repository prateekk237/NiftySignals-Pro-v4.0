"""
Signal Accuracy + Trade Manager endpoints.
"""

from fastapi import APIRouter, Query
from typing import Optional
from services.signal_logger import get_accuracy_stats, get_recent_signals
from services.trade_manager import is_expiry_day, TRAIL_STAGES
from services.telegram_service import telegram

router = APIRouter(prefix="/api", tags=["accuracy"])


@router.get("/accuracy")
async def signal_accuracy(
    days: int = Query(7, ge=1, le=90),
    symbol: Optional[str] = Query(None),
):
    """Get signal accuracy statistics."""
    return get_accuracy_stats(days=days, symbol=symbol)


@router.get("/signals/log")
async def signal_log(
    limit: int = Query(20, ge=1, le=100),
    symbol: Optional[str] = Query(None),
):
    """Get recent signal log entries."""
    return get_recent_signals(limit=limit, symbol=symbol)


@router.get("/expiry-check")
async def expiry_check(
    symbol: str = Query("NIFTY50", pattern="^(NIFTY50|BANKNIFTY)$"),
):
    """Check if today is expiry day and get adjustments."""
    return is_expiry_day(symbol)


@router.get("/trail-config")
async def trail_config():
    """Get trailing SL stage configuration."""
    return TRAIL_STAGES


# ── Telegram Config ──────────────────────────────────────────

@router.post("/telegram/configure")
async def configure_telegram(data: dict):
    """Configure or update Telegram bot for alerts."""
    bot_token = data.get("bot_token", "")
    chat_id = data.get("chat_id", "")
    if not bot_token or not chat_id:
        return {"error": "bot_token and chat_id required"}

    telegram.configure(bot_token, chat_id)

    # Test message
    ok = await telegram.send("✅ NiftySignals Pro connected!\n\nSend /help to see all commands.")
    return {
        "configured": True,
        "status": "configured" if ok else "configured_but_test_failed",
        "chat_id_masked": chat_id[:4] + "***",
        "token_masked": bot_token[:8] + "***" + bot_token[-4:] if len(bot_token) > 12 else "***",
        "test_sent": ok,
    }


@router.patch("/telegram/configure")
async def update_telegram(data: dict):
    """Update Telegram bot_token and/or chat_id."""
    bot_token = data.get("bot_token", telegram.bot_token or "")
    chat_id = data.get("chat_id", telegram.chat_id or "")
    if not bot_token or not chat_id:
        return {"error": "bot_token and chat_id required"}

    telegram.configure(bot_token, chat_id)

    ok = await telegram.send("✅ Telegram config updated!")
    return {
        "configured": True,
        "status": "updated" if ok else "updated_but_test_failed",
        "chat_id_masked": chat_id[:4] + "***",
        "token_masked": bot_token[:8] + "***" + bot_token[-4:] if len(bot_token) > 12 else "***",
        "test_sent": ok,
    }


@router.delete("/telegram/configure")
async def disconnect_telegram():
    """Disconnect Telegram bot — stops all alerts and command polling."""
    was_configured = telegram.is_configured
    if was_configured:
        await telegram.send("👋 NiftySignals disconnected. Alerts stopped.")
    telegram.disconnect()
    return {
        "configured": False,
        "status": "disconnected",
        "was_configured": was_configured,
    }


@router.get("/telegram/status")
async def telegram_status():
    """Check Telegram configuration status with masked credentials."""
    if not telegram.is_configured:
        return {"configured": False, "chat_id_masked": None, "token_masked": None}
    token = telegram.bot_token or ""
    return {
        "configured": True,
        "chat_id_masked": (telegram.chat_id[:4] + "***") if telegram.chat_id else None,
        "token_masked": token[:8] + "***" + token[-4:] if len(token) > 12 else "***",
    }


@router.post("/telegram/test")
async def telegram_test():
    """Send a test message to Telegram."""
    if not telegram.is_configured:
        return {"error": "Not configured. POST /api/telegram/configure first."}
    ok = await telegram.send("🧪 Test from NiftySignals Pro!\nAlerts are working. Send /help for commands.")
    return {"sent": ok}
