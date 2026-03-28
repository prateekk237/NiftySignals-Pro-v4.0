"""
Telegram Alert Service — Push signals and alerts to your phone.

Setup:
  1. Create bot via @BotFather on Telegram → get BOT_TOKEN
  2. Start a chat with your bot, send /start
  3. Get your CHAT_ID via https://api.telegram.org/bot<TOKEN>/getUpdates
  4. Add both to Settings page (stored in SQLite)

Sends alerts for:
  - New BUY CE / BUY PE signals (confluence + quick)
  - BTST predictions (3 PM)
  - Trailing SL stage changes
  - SL/Target hits
  - Expiry day warnings
"""

import logging
import asyncio
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self):
        self.bot_token: Optional[str] = None
        self.chat_id: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    def configure(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._client = httpx.AsyncClient(timeout=10)
        logger.info(f"Telegram configured: chat_id={chat_id[:6]}***")

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.is_configured:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            resp = await self._client.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            })
            if resp.status_code == 200:
                return True
            logger.warning(f"Telegram send failed: {resp.status_code} {resp.text[:100]}")
            return False
        except Exception as e:
            logger.warning(f"Telegram error: {e}")
            return False

    # ── Alert formatters ──────────────────────────────────────

    async def alert_signal(self, signal_type: str, symbol: str, data: dict):
        """Send signal alert."""
        action = data.get("action", "")
        if action in ["NO TRADE", "NO SIGNAL"]:
            return

        conf = data.get("confidence", 0)
        score = data.get("confluence_score", data.get("score", 0))
        strike = data.get("strike", 0)
        entry = data.get("entry_premium", 0)
        sl = data.get("sl_premium", 0)
        t1 = data.get("target1_premium", 0)
        rr = data.get("risk_reward", 0)

        emoji = "🟢" if "CE" in action else "🔴"
        type_label = {"CONFLUENCE": "📊 CONFLUENCE", "QUICK": "⚡ QUICK 5M", "BTST": "🔮 BTST"}.get(signal_type, signal_type)

        msg = (
            f"{emoji} <b>{type_label} — {symbol}</b>\n"
            f"<b>{action}</b> | Conf: {conf:.0f}%\n"
            f"Strike: {strike} | Entry: ₹{entry}\n"
            f"SL: ₹{sl} | T1: ₹{t1}\n"
        )
        if rr:
            msg += f"R:R 1:{rr}\n"
        if score:
            msg += f"Score: {score:+.3f}\n"

        await self.send(msg)

    async def alert_trailing_sl(self, pos_id: int, symbol: str, stage: str, sl: float, pnl_pct: float):
        """Alert on trailing SL stage change."""
        stage_emoji = {"BREAKEVEN": "🟡", "T1_TRAIL": "🟢", "T2_TRAIL": "🟢🟢"}.get(stage, "⬜")
        msg = (
            f"{stage_emoji} <b>TRAIL SL #{pos_id} — {symbol}</b>\n"
            f"Stage: {stage} | SL moved to ₹{sl}\n"
            f"Current P&L: {pnl_pct:+.1f}%"
        )
        await self.send(msg)

    async def alert_exit(self, pos_id: int, symbol: str, exit_type: str, pnl_pct: float, premium: float):
        """Alert on SL hit or target hit."""
        emoji = "🛑" if "SL" in exit_type else "🎯"
        msg = (
            f"{emoji} <b>{exit_type} #{pos_id} — {symbol}</b>\n"
            f"LTP: ₹{premium} | P&L: {pnl_pct:+.1f}%"
        )
        await self.send(msg)

    async def alert_btst(self, symbol: str, data: dict):
        """BTST prediction alert at 3 PM."""
        pred = data.get("prediction", "")
        emoji = data.get("emoji", "")
        score = data.get("score", 0)
        conf = data.get("confidence", 0)
        factors = data.get("factors_with_data", 0)
        trade = data.get("btst_trade", {})

        msg = (
            f"{emoji} <b>BTST — {symbol}</b>\n"
            f"<b>{pred}</b> | Score: {score:+.3f} | Conf: {conf:.0f}%\n"
            f"Factors: {factors}/10\n"
        )
        if trade:
            msg += f"\n{trade.get('action', '')} | {trade.get('entry_time', '')}"

        await self.send(msg)

    async def alert_expiry_warning(self, symbol: str, expiry_type: str):
        """Expiry day morning warning."""
        msg = (
            f"⚠️ <b>{expiry_type} EXPIRY DAY — {symbol}</b>\n"
            f"Theta decay accelerating.\n"
            f"• Tighter targets after 12 PM\n"
            f"• No new BUY after 1:30 PM\n"
            f"• Prefer ITM strikes"
        )
        await self.send(msg)


# Singleton
telegram = TelegramService()
