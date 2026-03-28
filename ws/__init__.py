"""
WebSocket server — python-socketio with all event emitters.
Sprint 3: All 10 WebSocket events defined here.
"""

import socketio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Create Socket.IO async server
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",  # Overridden by CORS middleware in main.py
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
)


# ── Connection Events ─────────────────────────────────────────

@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")
    await sio.emit("connection_ack", {"status": "connected", "sid": sid}, to=sid)


@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")


@sio.event
async def subscribe(sid, data):
    """Client subscribes to a symbol's updates."""
    symbol = data.get("symbol", "NIFTY50")
    await sio.enter_room(sid, f"symbol:{symbol}")
    logger.info(f"Client {sid} subscribed to {symbol}")


@sio.event
async def unsubscribe(sid, data):
    symbol = data.get("symbol", "NIFTY50")
    await sio.leave_room(sid, f"symbol:{symbol}")
    logger.info(f"Client {sid} unsubscribed from {symbol}")


# ── Emit Helpers (called by scheduler jobs) ───────────────────

class WSEmitter:
    """
    Centralized WebSocket emitter.
    All scheduler jobs call these methods to push data to clients.
    """

    # Sprint 3.2 — price_update (every 1s)
    async def emit_price_update(self, data: dict, symbol: str = "NIFTY50"):
        """Emit live price + VIX to all clients."""
        await sio.emit("price_update", {
            "event": "price_update",
            **data,
        })

    # Sprint 3.3 — option_ltp_update (every 3s)
    async def emit_option_ltp_update(self, data: dict):
        await sio.emit("option_ltp_update", {
            "event": "option_ltp_update",
            **data,
        })

    # Sprint 3.4 — signal_update (every 60s)
    async def emit_signal_update(self, data: dict):
        await sio.emit("signal_update", {
            "event": "signal_update",
            **data,
        })

    # Sprint 3.5 — quick_signal_update (every 15s)
    async def emit_quick_signal_update(self, data: dict):
        await sio.emit("quick_signal_update", {
            "event": "quick_signal_update",
            **data,
        })

    # Sprint 3.6 — btst_update (every 5min)
    async def emit_btst_update(self, data: dict):
        await sio.emit("btst_update", {
            "event": "btst_update",
            **data,
        })

    # Sprint 3.7 — alert_update (every 15s)
    async def emit_alert_update(self, data: dict):
        await sio.emit("alert_update", {
            "event": "alert_update",
            **data,
        })

    # Sprint 3.8 — btst_sl_alert + btst_target_alert (on trigger)
    async def emit_btst_sl_alert(self, data: dict):
        await sio.emit("btst_sl_alert", {
            "event": "btst_sl_alert",
            **data,
        })

    async def emit_btst_target_alert(self, data: dict):
        await sio.emit("btst_target_alert", {
            "event": "btst_target_alert",
            **data,
        })

    # oi_update (every 15s)
    async def emit_oi_update(self, data: dict):
        await sio.emit("oi_update", {
            "event": "oi_update",
            **data,
        })

    # Sprint 3.9 — candle_update (every interval)
    async def emit_candle_update(self, data: dict):
        await sio.emit("candle_update", {
            "event": "candle_update",
            **data,
        })

    # global_update (every 5min)
    async def emit_global_update(self, data: dict):
        await sio.emit("global_update", {
            "event": "global_update",
            **data,
        })

    # news_update (every 3min)
    async def emit_news_update(self, data: dict):
        await sio.emit("news_update", {
            "event": "news_update",
            **data,
        })

    # vix_analysis_update (every 60s)
    async def emit_vix_analysis_update(self, data: dict):
        await sio.emit("vix_analysis_update", {
            "event": "vix_analysis_update",
            **data,
        })

    # vix_history_update (every 10min)
    async def emit_vix_history_update(self, data: dict):
        await sio.emit("vix_history_update", {
            "event": "vix_history_update",
            **data,
        })

    # levels_update (once at 9:15 AM)
    async def emit_levels_update(self, data: dict):
        await sio.emit("levels_update", {
            "event": "levels_update",
            **data,
        })


# Singleton emitter
ws_emitter = WSEmitter()
