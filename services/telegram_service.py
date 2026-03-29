"""
Telegram Alert Service v2 — Two-way interactive bot.

OUTBOUND alerts (auto-pushed):
  - New BUY CE / BUY PE signals (confluence + quick)
  - BTST predictions (3 PM)
  - Trailing SL stage changes
  - SL/Target hits
  - Expiry day warnings

INBOUND commands (user sends to bot):
  /price     — NIFTY & BANKNIFTY live price
  /signal    — Latest confluence signal
  /quick     — Latest quick 5-min signal
  /btst      — Today's BTST prediction
  /vix       — India VIX + zone + analysis
  /oi        — PCR, max pain, OI bias
  /positions — Open BTST positions
  /pnl       — P&L summary
  /global    — Global market score + indices
  /news      — Latest headlines with sentiment
  /alerts    — Active alerts
  /levels    — CPR + ORB levels
  /health    — System status
  /help      — Show all commands
"""

import json
import os
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
        self._last_update_id: int = 0

    # ── Config Persistence ─────────────────────────────────────

    def configure(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._client = httpx.AsyncClient(timeout=10)
        self._last_update_id = 0
        self._save_config()
        logger.info(f"Telegram configured: chat_id={chat_id[:6]}***")

    def _save_config(self):
        """Persist telegram config to JSON file so it survives restarts."""
        try:
            data = {
                "bot_token": self.bot_token,
                "chat_id": self.chat_id,
                "last_update_id": self._last_update_id,
            }
            # Try /data first (Railway volume), fallback to local
            for path in ["/data/telegram_config.json", "telegram_config.json"]:
                try:
                    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                    with open(path, "w") as f:
                        json.dump(data, f)
                    logger.info(f"Telegram config saved to {path}")
                    return
                except OSError:
                    continue
        except Exception as e:
            logger.warning(f"Failed to save telegram config: {e}")

    def load_config(self):
        """Load telegram config from file on startup."""
        for path in ["/data/telegram_config.json", "telegram_config.json"]:
            try:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        data = json.load(f)
                    if data.get("bot_token") and data.get("chat_id"):
                        self.bot_token = data["bot_token"]
                        self.chat_id = data["chat_id"]
                        self._last_update_id = data.get("last_update_id", 0)
                        self._client = httpx.AsyncClient(timeout=10)
                        logger.info(f"Telegram config loaded from {path}")
                        return True
            except Exception as e:
                logger.warning(f"Failed to load telegram config from {path}: {e}")
        return False

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    # ── Send Message ───────────────────────────────────────────

    async def send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.is_configured:
            return False
        try:
            if not self._client:
                self._client = httpx.AsyncClient(timeout=10)
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

    # ── Poll for Commands ──────────────────────────────────────

    async def poll_updates(self):
        """Check for new messages and handle commands. Called by scheduler."""
        if not self.is_configured:
            return

        try:
            if not self._client:
                self._client = httpx.AsyncClient(timeout=10)
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {"offset": self._last_update_id + 1, "timeout": 0, "limit": 10}
            resp = await self._client.get(url, params=params, timeout=5)

            if resp.status_code != 200:
                return

            data = resp.json()
            if not data.get("ok") or not data.get("result"):
                return

            for update in data["result"]:
                self._last_update_id = update["update_id"]
                msg = update.get("message", {})
                text = msg.get("text", "").strip()
                chat_id = str(msg.get("chat", {}).get("id", ""))

                # Only respond to the configured chat
                if chat_id != self.chat_id:
                    continue

                if text.startswith("/"):
                    await self._handle_command(text)

            # Save last_update_id so we don't re-process on restart
            self._save_config()

        except httpx.TimeoutException:
            pass
        except Exception as e:
            logger.warning(f"Telegram poll error: {e}")

    # ── Command Router ─────────────────────────────────────────

    async def _handle_command(self, text: str):
        """Route commands to handlers."""
        cmd = text.split()[0].lower().split("@")[0]  # strip @botname

        handlers = {
            "/start": self._cmd_help,
            "/help": self._cmd_help,
            "/price": self._cmd_price,
            "/p": self._cmd_price,
            "/signal": self._cmd_signal,
            "/s": self._cmd_signal,
            "/quick": self._cmd_quick,
            "/q": self._cmd_quick,
            "/btst": self._cmd_btst,
            "/b": self._cmd_btst,
            "/vix": self._cmd_vix,
            "/v": self._cmd_vix,
            "/oi": self._cmd_oi,
            "/positions": self._cmd_positions,
            "/pos": self._cmd_positions,
            "/pnl": self._cmd_pnl,
            "/global": self._cmd_global,
            "/g": self._cmd_global,
            "/news": self._cmd_news,
            "/n": self._cmd_news,
            "/alerts": self._cmd_alerts,
            "/a": self._cmd_alerts,
            "/levels": self._cmd_levels,
            "/l": self._cmd_levels,
            "/health": self._cmd_health,
        }

        handler = handlers.get(cmd)
        if handler:
            try:
                await handler()
            except Exception as e:
                logger.error(f"Command {cmd} error: {e}")
                await self.send(f"❌ Error: {str(e)[:100]}")
        else:
            await self.send(
                "❓ Unknown command. Send /help for list."
            )

    # ── Command Handlers ───────────────────────────────────────

    async def _cmd_help(self):
        msg = (
            "📱 <b>NiftySignals Pro v4.0</b>\n\n"
            "📊 <b>Market Data</b>\n"
            "/price — NIFTY & BANKNIFTY price\n"
            "/vix — India VIX + zone\n"
            "/oi — PCR, Max Pain, OI bias\n"
            "/global — Global indices score\n"
            "/levels — CPR + ORB levels\n"
            "/news — Latest headlines\n\n"
            "🎯 <b>Signals</b>\n"
            "/signal — Confluence signal\n"
            "/quick — Quick 5-min signal\n"
            "/btst — BTST prediction\n"
            "/alerts — Active alerts\n\n"
            "💰 <b>Trades</b>\n"
            "/positions — Open positions\n"
            "/pnl — P&L summary\n\n"
            "⚙️ <b>System</b>\n"
            "/health — System status\n\n"
            "💡 <i>Shortcuts: /p /s /q /b /v /g /n /a /l /pos</i>"
        )
        await self.send(msg)

    async def _cmd_price(self):
        from core.cache import cache

        nifty = cache.get("price:NIFTY50")
        bnf = cache.get("price:BANKNIFTY")
        vix = cache.get("vix:live")

        msg = "📊 <b>LIVE PRICES</b>\n\n"

        if nifty:
            chg = nifty.get("change_pct", 0)
            emoji = "🟢" if chg >= 0 else "🔴"
            msg += (
                f"{emoji} <b>NIFTY 50</b>\n"
                f"   ₹{nifty['price']:,.2f} ({chg:+.2f}%)\n"
                f"   H: {nifty.get('high', 0):,.0f} · L: {nifty.get('low', 0):,.0f}\n\n"
            )
        else:
            msg += "⏸ NIFTY: No data\n\n"

        if bnf:
            chg = bnf.get("change_pct", 0)
            emoji = "🟢" if chg >= 0 else "🔴"
            msg += (
                f"{emoji} <b>BANK NIFTY</b>\n"
                f"   ₹{bnf['price']:,.2f} ({chg:+.2f}%)\n"
                f"   H: {bnf.get('high', 0):,.0f} · L: {bnf.get('low', 0):,.0f}\n\n"
            )
        else:
            msg += "⏸ BANKNIFTY: No data\n\n"

        if vix:
            v = vix.get("vix", 0)
            zone = "LOW" if v < 14 else "NORMAL" if v < 20 else "HIGH"
            msg += f"📈 <b>VIX</b>: {v:.2f} ({zone})"
        else:
            msg += "📈 VIX: No data"

        await self.send(msg)

    async def _cmd_signal(self):
        from core.cache import cache

        sent = False
        for sym in ["NIFTY50", "BANKNIFTY"]:
            data = cache.get(f"signal:{sym}")
            if not data:
                continue

            action = data.get("action", "NO TRADE")
            if action == "NO TRADE":
                emoji = "⏸"
            elif "CE" in action:
                emoji = "🟢"
            else:
                emoji = "🔴"

            msg = (
                f"{emoji} <b>CONFLUENCE — {sym}</b>\n"
                f"<b>{action}</b>\n"
                f"Score: {data.get('confluence_score', 0):+.3f}\n"
                f"Confidence: {data.get('confidence', 0):.0f}%\n"
            )

            if action != "NO TRADE":
                msg += (
                    f"Strike: {data.get('strike', '—')}\n"
                    f"Entry: ₹{data.get('entry_premium', 0):.1f}\n"
                    f"SL: ₹{data.get('sl_premium', 0):.1f} · T1: ₹{data.get('target1_premium', 0):.1f}\n"
                )

            comps = data.get("components", {})
            if comps:
                top = sorted(comps.items(), key=lambda x: abs(x[1]), reverse=True)[:4]
                msg += "\n"
                for name, val in top:
                    arrow = "▲" if val > 0 else "▼" if val < 0 else "—"
                    msg += f"  {arrow} {name}: {val:+.3f}\n"

            await self.send(msg)
            sent = True

        if not sent:
            await self.send("⏸ No confluence signal data available.")

    async def _cmd_quick(self):
        from core.cache import cache

        sent = False
        for sym in ["NIFTY50", "BANKNIFTY"]:
            data = cache.get(f"quick_signal:{sym}")
            if not data:
                continue

            has_signal = data.get("has_signal", False)
            action = data.get("action", "")

            if has_signal:
                emoji = "🟢" if "CE" in action else "🔴"
                msg = (
                    f"{emoji} <b>⚡ QUICK — {sym}</b>\n"
                    f"<b>{action}</b>\n"
                    f"Confidence: {data.get('confidence', 0):.0f}%\n"
                    f"Strike: {data.get('strike', '—')}\n"
                    f"Entry: ₹{data.get('entry_premium', 0):.1f}\n"
                )
                if data.get("risk_reward"):
                    msg += f"R:R 1:{data['risk_reward']}\n"
                if data.get("agreement"):
                    msg += f"Agreement: {data['agreement']}\n"
            else:
                msg = (
                    f"⏸ <b>⚡ QUICK — {sym}</b>\n"
                    f"No signal: {data.get('reason', 'Waiting')}\n"
                )

            # Indicator status
            for ind in ["supertrend", "vwap", "rsi"]:
                d = data.get(ind, {})
                if d:
                    s = d.get("signal", 0)
                    arrow = "🟢" if s > 0 else "🔴" if s < 0 else "⚪"
                    msg += f"  {arrow} {ind.upper()}: {d.get('detail', '')}\n"

            if data.get("adx", 0) > 0:
                adx = data["adx"]
                msg += f"  {'🟢' if adx > 25 else '🟡' if adx > 20 else '🔴'} ADX: {adx:.1f}\n"

            await self.send(msg)
            sent = True

        if not sent:
            await self.send("⏸ No quick signal data available.")

    async def _cmd_btst(self):
        from core.cache import cache

        for sym in ["NIFTY50", "BANKNIFTY"]:
            data = cache.get(f"btst:{sym}")
            if not data:
                continue

            pred = data.get("prediction", "NO DATA")
            if pred in ["WEEKEND", "TOO EARLY", "NO DATA"]:
                await self.send(
                    f"{data.get('emoji', '⏸')} <b>BTST — {sym}</b>\n"
                    f"{pred}\n"
                    f"{data.get('best_check_time', 'Check at 3 PM IST')}"
                )
                return

            emoji = data.get("emoji", "")
            score = data.get("score", 0)
            conf = data.get("confidence", 0)

            msg = (
                f"{emoji} <b>BTST — {sym}</b>\n"
                f"<b>{pred}</b>\n"
                f"Score: {score:+.3f} · Conf: {conf:.0f}%\n"
                f"Factors: {data.get('factors_with_data', '?')}/10\n"
            )

            # GIFT NIFTY
            gift = data.get("gift_nifty", {})
            if gift and gift.get("estimated_price", 0) > 0:
                msg += (
                    f"\n🌙 <b>GIFT NIFTY</b>\n"
                    f"Est: {gift['estimated_price']:,.0f} "
                    f"({gift.get('change_pts', 0):+.0f} pts, {gift.get('change_pct', 0)}%)\n"
                    f"Range: {gift.get('gap_range_low', 0):,.0f} — {gift.get('gap_range_high', 0):,.0f}\n"
                )

            # Trade suggestion
            trade = data.get("btst_trade", {})
            if trade:
                msg += (
                    f"\n💡 {trade.get('action', '')}\n"
                    f"SL: {trade.get('sl', '')} · T: {trade.get('target', '')}\n"
                )

            # Gap risk
            gap = data.get("gap_day_info", {})
            if gap and gap.get("risk_score", 0) >= 2:
                msg += f"\n⚡ {gap.get('risk_label', '')} GAP RISK"

            await self.send(msg)
            return

        await self.send("⏸ No BTST data. Check after 3 PM IST.")

    async def _cmd_vix(self):
        from core.cache import cache

        vix_live = cache.get("vix:live") or {}
        vix_analysis = cache.get("vix:analysis") or {}
        vix = vix_live.get("vix", 0)

        if not vix:
            await self.send("⏸ VIX data not available.")
            return

        zone = "XLOW" if vix < 12 else "LOW" if vix < 14 else "NORMAL" if vix < 18 else "ELEVATED" if vix < 22 else "HIGH"
        chg = vix_live.get("vix_change", 0)

        msg = (
            f"📈 <b>INDIA VIX</b>\n\n"
            f"<b>{vix:.2f}</b> ({chg:+.2f}%) — {zone}\n\n"
        )

        if vix_analysis:
            msg += (
                f"1D: {vix_analysis.get('change_1d', 0):+.2f}%\n"
                f"5D: {vix_analysis.get('change_5d', 0):+.2f}%\n"
                f"Percentile: {vix_analysis.get('percentile', 0):.0f}\n"
            )
            if vix_analysis.get("strategy_advice"):
                msg += f"\n💡 {vix_analysis['strategy_advice']}\n"
            if vix_analysis.get("spike_alert"):
                msg += "\n🚨 <b>VIX SPIKE DETECTED!</b>\n"

        await self.send(msg)

    async def _cmd_oi(self):
        from core.cache import cache

        for sym in ["NIFTY50", "BANKNIFTY"]:
            data = cache.get(f"oi:{sym}")
            if not data or not data.get("pcr"):
                continue

            pcr = data.get("pcr", 0)
            bias = data.get("oi_bias", "—")
            max_pain = data.get("max_pain", 0)

            pcr_emoji = "🟢" if pcr > 1 else "🔴" if pcr < 0.7 else "🟡"
            bias_emoji = "🟢" if bias == "BULLISH" else "🔴" if bias == "BEARISH" else "🟡"

            msg = (
                f"📋 <b>OI — {sym}</b>\n\n"
                f"{pcr_emoji} PCR: {pcr:.3f}\n"
                f"{bias_emoji} Bias: {bias}\n"
                f"🎯 Max Pain: {max_pain:,}\n"
            )

            support = data.get("support", [])
            resistance = data.get("resistance", [])
            if support:
                msg += f"\n🟢 Support: {', '.join(str(s) for s in support)}\n"
            if resistance:
                msg += f"🔴 Resistance: {', '.join(str(r) for r in resistance)}\n"

            await self.send(msg)
            return

        await self.send("⏸ OI data available during market hours only.")

    async def _cmd_positions(self):
        from core.database import SessionLocal
        from models import BTSTPosition

        try:
            db = SessionLocal()
            try:
                open_pos = db.query(BTSTPosition).filter(
                    BTSTPosition.status == "OPEN"
                ).order_by(BTSTPosition.id.desc()).all()

                if not open_pos:
                    await self.send("📭 No open positions.")
                    return

                msg = f"💰 <b>OPEN POSITIONS ({len(open_pos)})</b>\n\n"
                for p in open_pos[:10]:
                    opt_emoji = "🟢" if p.option_type == "CE" else "🔴"
                    trail = ""
                    if p.trail_stage and p.trail_stage != "ENTRY":
                        trail = f" · 🛡{p.trail_stage} SL₹{p.trailing_sl}"

                    msg += (
                        f"{opt_emoji} <b>#{p.id} {p.symbol} {p.option_type}</b>\n"
                        f"   Strike: {p.strike_price or '—'} · Entry: ₹{p.entry_premium}\n"
                        f"   {p.entry_date} {p.entry_time or ''}{trail}\n\n"
                    )

                await self.send(msg)
            finally:
                db.close()
        except Exception as e:
            await self.send(f"❌ Error: {e}")

    async def _cmd_pnl(self):
        from core.database import SessionLocal
        from models import BTSTPosition

        try:
            db = SessionLocal()
            try:
                all_pos = db.query(BTSTPosition).all()
                total = len(all_pos)
                open_count = sum(1 for p in all_pos if p.status == "OPEN")
                closed = [p for p in all_pos if p.status != "OPEN"]
                wins = sum(1 for p in closed if p.pnl_rupees and p.pnl_rupees > 0)
                losses = sum(1 for p in closed if p.pnl_rupees and p.pnl_rupees <= 0)
                win_rate = (wins / len(closed) * 100) if closed else 0
                total_pnl = sum(p.pnl_rupees for p in closed if p.pnl_rupees) or 0
                best = max((p.pnl_pct for p in closed if p.pnl_pct is not None), default=0)
                worst = min((p.pnl_pct for p in closed if p.pnl_pct is not None), default=0)

                pnl_emoji = "🟢" if total_pnl > 0 else "🔴" if total_pnl < 0 else "⚪"

                msg = (
                    f"📊 <b>P&L SUMMARY</b>\n\n"
                    f"Total: {total} · Open: {open_count}\n"
                    f"Wins: {wins} · Losses: {losses}\n"
                    f"Win Rate: {win_rate:.1f}%\n\n"
                    f"{pnl_emoji} <b>Total P&L: ₹{total_pnl:+,.0f}</b>\n"
                    f"Best: {best:+.1f}% · Worst: {worst:+.1f}%\n"
                )

                await self.send(msg)
            finally:
                db.close()
        except Exception as e:
            await self.send(f"❌ Error: {e}")

    async def _cmd_global(self):
        from core.cache import cache

        score_data = cache.get("global:score")
        indian = cache.get("global:indian_indices")
        raw = cache.get("global:data")

        if not score_data:
            await self.send("⏸ Global data not available.")
            return

        score = score_data.get("score", 0)
        label = score_data.get("label", "")
        emoji = "🟢" if score > 0 else "🔴" if score < 0 else "🟡"

        msg = (
            f"🌍 <b>GLOBAL MARKETS</b>\n\n"
            f"{emoji} Score: <b>{score:+.3f}</b> — {label}\n\n"
        )

        # Indian indices
        if indian:
            msg += "<b>🇮🇳 Indian</b>\n"
            for name, data in list(indian.items())[:5]:
                chg = data.get("change_pct", 0)
                arrow = "▲" if chg > 0 else "▼" if chg < 0 else "—"
                msg += f"  {arrow} {name}: {chg:+.2f}%\n"
            msg += "\n"

        # Global from raw
        if raw and isinstance(raw, dict):
            groups = {}
            for name, info in raw.items():
                if isinstance(info, dict):
                    grp = info.get("group", "Other")
                    if grp not in groups:
                        groups[grp] = []
                    groups[grp].append(info)

            for grp, indices in list(groups.items())[:3]:
                msg += f"<b>{grp}</b>\n"
                for idx in indices[:4]:
                    chg = idx.get("change_pct", 0)
                    arrow = "▲" if chg > 0 else "▼" if chg < 0 else "—"
                    msg += f"  {arrow} {idx.get('name', '?')}: {chg:+.2f}%\n"
                msg += "\n"

        await self.send(msg)

    async def _cmd_news(self):
        from core.cache import cache

        score_data = cache.get("news:score") or {}
        headlines = cache.get("news:headlines") or []

        score = score_data.get("score", 0)
        label = score_data.get("label", "")

        emoji = "🟢" if score > 0.1 else "🔴" if score < -0.1 else "🟡"
        msg = f"📰 <b>NEWS SENTIMENT</b>\n\n{emoji} Score: {score:+.3f} — {label}\n\n"

        if headlines:
            for h in headlines[:8]:
                s = h.get("sentiment", 0)
                arrow = "▲" if s > 0.1 else "▼" if s < -0.1 else "—"
                title = h.get("title", "")[:80]
                msg += f"{arrow} {title}\n"
        else:
            msg += "No recent headlines."

        await self.send(msg)

    async def _cmd_alerts(self):
        from core.cache import cache

        found = False
        for sym in ["NIFTY50", "BANKNIFTY"]:
            data = cache.get(f"alerts:{sym}")
            if not data:
                continue

            alerts = data if isinstance(data, list) else data.get("alerts", [])
            if not alerts:
                continue

            msg = f"🚨 <b>ALERTS — {sym}</b>\n\n"
            for a in alerts[:8]:
                sev = a.get("severity", "INFO")
                sev_emoji = "🔴" if sev == "CRITICAL" else "🟠" if sev == "HIGH" else "🔵"
                msg += (
                    f"{sev_emoji} [{sev}] {a.get('type', '')}\n"
                    f"   {a.get('message', '')}\n\n"
                )

            await self.send(msg)
            found = True

        if not found:
            await self.send("✅ No active alerts.")

    async def _cmd_levels(self):
        from core.cache import cache

        for sym in ["NIFTY50", "BANKNIFTY"]:
            cpr = cache.get(f"cpr:{sym}")
            orb = cache.get(f"orb:{sym}")

            if not cpr and not orb:
                continue

            msg = f"📐 <b>LEVELS — {sym}</b>\n\n"

            if cpr:
                msg += "<b>CPR</b>\n"
                for label, key in [("R2", "r2"), ("R1", "r1"), ("Pivot", "pivot"), ("S1", "s1"), ("S2", "s2")]:
                    val = cpr.get(key)
                    if val:
                        msg += f"  {label}: {val:,.2f}\n"
                if cpr.get("is_narrow_cpr"):
                    msg += "  ⚡ NARROW CPR\n"
                msg += "\n"

            if orb and orb.get("orb_high", 0) > 0:
                msg += (
                    f"<b>ORB</b>\n"
                    f"  High: {orb['orb_high']:,.2f}\n"
                    f"  Low: {orb.get('orb_low', 0):,.2f}\n"
                )

            await self.send(msg)
            return

        await self.send("⏸ Level data available after 9:15 AM IST.")

    async def _cmd_health(self):
        from core.cache import cache
        from core.circuit_breaker import nse_breaker, yfinance_breaker, llm_breaker
        from services.llm_service import llm_service

        cache_status = cache.status()
        llm_count = len(llm_service.providers)

        breakers = []
        for b in [nse_breaker, yfinance_breaker, llm_breaker]:
            s = b.status()
            emoji = "🟢" if s["state"] == "CLOSED" else "🔴" if s["state"] == "OPEN" else "🟡"
            breakers.append(f"  {emoji} {s['name']}: {s['state']} ({s['failures']}/{s['threshold']})")

        msg = (
            f"⚙️ <b>SYSTEM HEALTH</b>\n\n"
            f"📦 Cache: {cache_status['active_keys']} keys\n"
            f"🤖 LLM: {llm_count} providers\n\n"
            f"<b>Circuit Breakers</b>\n"
            + "\n".join(breakers)
        )

        await self.send(msg)

    # ── Outbound Alert Formatters (existing) ───────────────────

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
