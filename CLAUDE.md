# NiftySignals Pro v4.0 — Project Context File
# Last updated: March 30, 2026

## What This Project Is

A production-grade real-time Indian F&O trading signal dashboard for NIFTY50 and BANKNIFTY.
Fully migrated from Streamlit to FastAPI + React + WebSocket. Deployed on Railway.

**Live URL:** `https://web-production-1b988.up.railway.app`
**GitHub:** `github.com/prateekk237/NiftySignals-Pro-v4.0`
**Architecture:** FastAPI backend serves both API + frontend HTML from single Railway URL.

---

## MIGRATION STATUS: 100% COMPLETE

All 7 original sprints (70 tasks) completed. Plus 3 bonus sprints for strategy upgrades, trade management, and production fixes. Plus Sprint 11 for Telegram interactive bot, signal safety fixes, and Sprint 11.1 for indicator visibility + Telegram CRUD.

---

## CURRENT ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│  BROWSER (Single HTML bundle)                                │
│  React 18 + shadcn/ui + Tailwind CSS (dark terminal theme)  │
│  3 pages: Dashboard | BTST History | Settings               │
│  WebSocket (Socket.IO) for real-time push                   │
│  REST fallback every 30s for data that missed WS            │
└──────────────────┬──────────────────────────────────────────┘
                   │ wss:// (Socket.IO) + https:// (REST)
                   │ Same origin — no CORS issues
┌──────────────────▼──────────────────────────────────────────┐
│  FASTAPI BACKEND (Railway)                                   │
│  uvicorn + python-socketio (ASGI)                           │
│  APScheduler — 14 independent background jobs (1s → daily)  │
│  In-memory cache (dict) with TTL per key                    │
│  SQLAlchemy + SQLite (positions + signal logs + API keys)   │
│  static/index.html served at / (frontend bundled in)        │
│                                                              │
│  Services: 11 async wrappers around original Python files   │
│  Routers: 8 (market, signals, positions, candles, strikes,  │
│           api_keys, system, signals_accuracy)                │
│  Endpoints: 25+ REST endpoints                              │
│  WebSocket: 12+ event types                                 │
│  Telegram: 2-way interactive bot (13 commands + alerts)     │
└─────────────────────────────────────────────────────────────┘
```

---

## TECH STACK (Actual, not planned)

### Backend
- FastAPI + uvicorn (ASGI)
- python-socketio (WebSocket, Socket.IO protocol)
- APScheduler BackgroundScheduler (14 jobs)
- SQLAlchemy + SQLite with WAL mode (3 tables)
- In-memory dict cache with TTL
- Circuit breakers (NSE, yfinance, LLM)
- httpx (Telegram alerts + command polling)
- All original: yfinance, pandas, numpy, feedparser, vaderSentiment, openai

### Frontend
- React 18 (single-file JSX bundle via Parcel)
- shadcn/ui components (Card, Badge, Table, Dialog, Select, etc.)
- Tailwind CSS (terminal dark theme, JetBrains Mono)
- Native WebSocket (Socket.IO protocol)
- Error Boundaries on every panel

### Deploy
- Railway — single service (backend + frontend bundled)
- **IMPORTANT: Requires Railway persistent volume mounted at `/data`** for SQLite + Telegram config
- No separate Vercel needed — `static/index.html` served by FastAPI

---

## FILE STRUCTURE (Current)

```
backend/
├── main.py                          # FastAPI app, lifespan, health, serves frontend
│                                    # v4.1: Auto-loads Telegram config on startup
├── config.py                        # Original constants (unchanged)
├── data_fetcher.py                  # yfinance + NSE fetching (unchanged)
├── indicators.py                    # All technical indicators (unchanged)
├── signal_engine.py                 # v4: BUY-ONLY (no more SELL CE/PE)
├── quick_signals.py                 # v3: 5-gate filter, 2:1 R:R
├── btst_predictor.py                # v3: 10 factors + GIFT NIFTY proxy
├── sentiment.py                     # v4: 9 RSS feeds, freshness, dedup
├── global_analysis.py               # Batch yfinance fetch (unchanged)
├── realtime_alerts.py               # Exit alerts (unchanged)
├── llm_engine.py                    # NVIDIA NIM / OpenAI (unchanged)
│
├── core/
│   ├── config.py                    # Pydantic BaseSettings + env vars
│   ├── cache.py                     # Thread-safe in-memory cache with TTL
│   ├── circuit_breaker.py           # NSE/yfinance/LLM circuit breakers
│   └── database.py                  # SQLAlchemy + SQLite WAL mode
│
├── models/
│   ├── __init__.py                  # BTSTPosition + SignalLog models
│   └── api_key.py                   # APIKey model
│
├── schemas/
│   ├── __init__.py                  # Position CRUD schemas
│   └── api_key.py                   # API key schemas
│
├── services/
│   ├── data_fetcher.py              # Async wrapper
│   ├── indicator_service.py         # Indicator computation
│   ├── signal_service.py            # Confluence scoring
│   ├── btst_service.py              # BTST prediction (10 factors)
│   ├── global_service.py            # Global market analysis
│   ├── sentiment_service.py         # News sentiment
│   ├── alert_service.py             # Exit alerts
│   ├── quick_signal_service.py      # Quick scalping signals
│   ├── llm_service.py               # Multi-provider LLM fallback chain
│   ├── trade_manager.py             # Trailing SL + expiry day + partial exits
│   ├── signal_logger.py             # Auto-log signals + accuracy tracking
│   └── telegram_service.py          # v2: Two-way interactive bot + push alerts
│
├── schedulers/
│   └── jobs.py                      # 14 APScheduler jobs (asyncio.run wrapper)
│                                    # v4.1: indicators 24/7, signals market-hours only
│
├── routers/
│   ├── market.py                    # Price, VIX, OI, global, news, levels, indicators
│   ├── signals.py                   # Signal, quick-signal, BTST, alerts
│   ├── positions.py                 # BTST CRUD + CSV export + bulk delete
│   ├── candles.py                   # OHLCV for charts
│   ├── strikes.py                   # Strike autocomplete
│   ├── api_keys.py                  # LLM API key CRUD
│   ├── system.py                    # Circuit breakers, backup, cache
│   └── signals_accuracy.py          # Signal accuracy + Telegram CRUD + expiry
│
├── ws/
│   └── __init__.py                  # Socket.IO server + 12 event emitters
│
├── static/
│   └── index.html                   # Frontend bundle (React, served at /)
│
├── alembic/versions/
│   ├── 001_initial.py               # btst_positions table
│   ├── 002_api_keys.py              # api_keys table
│   └── 003_trade_manager.py         # signal_logs table + trailing SL columns
│
├── requirements.txt
├── Procfile
├── railway.toml
├── .env.example
└── README.md
```

---

## DATABASE TABLES (SQLite)

### btst_positions
Core trade tracking with trailing SL and partial exit support.
```
id, entry_date, entry_time, symbol, option_type, entry_premium, strike_price,
exit_premium, exit_date, exit_time, pnl_rupees, pnl_pct, status,
prediction, confidence, gap_day_flag, gap_risk_score, gap_risk_label,
holiday_name, days_to_next_trading, notes, created_at,
trailing_sl, highest_ltp, trail_stage, total_lots, exited_lots, partial_exits
```

### signal_logs
Auto-logged signal outcomes for accuracy tracking.
```
id, timestamp, signal_type, symbol, action, strike, entry_premium,
confidence, confluence_score, premium_30m, premium_60m, pnl_30m_pct,
pnl_60m_pct, outcome, max_favorable, max_adverse, is_expiry_day,
adx_at_signal, vix_at_signal, time_of_day, weekday
```

### api_keys
Persistent LLM provider keys with fallback chain.
```
id, provider, label, api_key_encrypted, base_url, model, priority,
is_active, rate_limit_rpm, total_calls, total_errors, last_error,
notes, created_at
```

### Telegram Config (JSON file, not in DB)
Stored at `/data/telegram_config.json` (Railway volume) or `telegram_config.json` (local).
Persists bot_token, chat_id, last_update_id across restarts.

---

## REST API ENDPOINTS (25+)

```
# Dashboard served at root
GET  /                                              # Frontend HTML

# Health
GET  /health                                        # Full system status

# Market Data (cache → yfinance fallback when closed)
GET  /api/price?symbol=NIFTY50                      # Live price or last close
GET  /api/vix                                       # India VIX
GET  /api/oi?symbol=NIFTY50                         # OI + PCR + max pain
GET  /api/option-chain?symbol=NIFTY50               # Full option chain
GET  /api/global                                    # 16 global indices + score
GET  /api/news                                      # News sentiment + headlines
GET  /api/indicators?symbol=NIFTY50                 # All technical indicators
GET  /api/levels?symbol=NIFTY50                     # CPR + ORB levels
GET  /api/vix/history                               # VIX 1-year history

# Signals
GET  /api/signal?symbol=NIFTY50                     # Confluence signal
GET  /api/quick-signal?symbol=NIFTY50               # Quick 5-min signal
GET  /api/btst?symbol=NIFTY50                       # BTST prediction
GET  /api/alerts?symbol=NIFTY50                     # Real-time exit alerts

# BTST Positions
GET  /api/positions                                 # List all
GET  /api/positions/open                            # Open only
GET  /api/positions/stats                           # Aggregate stats
POST /api/positions                                 # Create new
PATCH /api/positions/:id/exit                       # Exit position
POST /api/positions/bulk-delete                     # Bulk delete
GET  /api/positions/export/csv                      # CSV export

# API Keys (LLM)
GET  /api/keys                                      # List all
POST /api/keys                                      # Add new
PATCH /api/keys/:id                                 # Update
DELETE /api/keys/:id                                # Delete
POST /api/keys/test                                 # Test key

# Accuracy + Trade Management
GET  /api/accuracy                                  # Signal accuracy stats
GET  /api/signals/log                               # Recent signal log
GET  /api/expiry-check?symbol=NIFTY50               # Expiry day detection
GET  /api/trail-config                              # Trailing SL config

# Telegram Alerts
POST  /api/telegram/configure                       # Set bot token + chat ID
PATCH /api/telegram/configure                       # Update token and/or chat ID
DELETE /api/telegram/configure                      # Disconnect bot, delete config
GET   /api/telegram/status                          # Check config (masked credentials)
POST  /api/telegram/test                            # Send test message

# System Admin
GET  /api/system/circuit-breakers                   # Breaker status
POST /api/system/backup                             # SQLite backup
GET  /api/system/backup/download                    # Download DB file
POST /api/system/cache/clear                        # Clear cache
```

---

## STRATEGY ENGINES (All upgraded)

### Signal Engine v4 (signal_engine.py)
**BUY-ONLY engine.** Never generates SELL CE/PE (naked option selling = unlimited risk).
- Divides by PRESENT weight only (not total 1.0)
- Thresholds: BUY ≥ 0.15, STRONG BUY ≥ 0.35 (was 0.25/0.45)
- Removed abs() < 0.10 kill switch
- VIX dampening softened to ×0.92 max
- ST+RSI combo: agreement bonus instead of average×0.5
- **v4 FIX:** When VIX > 25 + weak signal → returns NO TRADE (was SELL CE/PE)
- **v4.1 FIX:** Indicators (RSI, MACD, ADX, etc.) computed 24/7 from yfinance history — always visible on dashboard even when market is closed. Only trade signal generation is gated to market hours.
- **Only valid actions:** `BUY CE`, `BUY PE`, `NO TRADE`
- Signal labels (STRONG BUY/BUY/SELL/STRONG SELL) = direction labels, not trade types
  - "SELL" label = bearish direction → generates `BUY PE` action
  - "BUY" label = bullish direction → generates `BUY CE` action

### Quick Signals v3 (quick_signals.py)
5-gate filter system — all must pass, any doubt = NO TRADE.
- Gate 0: Time filter (skip 9:15-9:30 and after 3:15)
- Gate 1: Trend (ADX ≥ 22 NIFTY / ≥ 20 BNF + 2/3 Supertrend + DI)
- Gate 2: Momentum (MACD histogram direction + RSI zone)
- Gate 3: Price (VWAP + Bollinger %B + candle body strength)
- Gate 4: Volume (above 20-period average)
- Gate 5: Safety (exhaustion detection + StochRSI + Heikin Ashi)
- R:R improved to 2:1 (SL 25%, T1 50%, T2 100%)
- Separate BankNifty thresholds

### BTST Predictor v3 (btst_predictor.py)
10-factor system with GIFT NIFTY proxy.
- US Futures 22%, FII/DII 13%, Technical 12%, Asian 12%
- NEW: European close 8%, News sentiment 5%, DXY+Crude 5%
- GIFT NIFTY proxy: NIFTY Close × (1 + weighted_global × 0.85 correlation)
- Gap day risk dampens score 15% on Fridays
- Confidence scales by data coverage
- Breaking news override (±15%)
- Runs after market close (removed market hours guard)

### Sentiment v4 (sentiment.py)
9 RSS feeds with freshness + deduplication.
- 8-hour freshness filter (skip stale headlines)
- Fuzzy word-overlap deduplication
- Recency-weighted scoring (newest = highest weight)
- High-impact keywords get 2-3x weight
- Breaking news detection (crash, circuit, emergency)
- NIFTY/BANKNIFTY relevance tagging
- 60+ financial lexicon terms for VADER

---

## TRADE MANAGEMENT (Tier 1 features)

### 1. Auto Trailing Stop-Loss
Position monitor (3s job) automatically moves SL upward:
```
ENTRY      → SL at -25% (initial)
BREAKEVEN  → +30% peak → SL moves to entry price (zero risk)
T1_TRAIL   → +50% peak → SL at +25% (locked profit)
T2_TRAIL   → +80% peak → SL at +50% (locked profit)
```
SL only moves UP, never down. BankNifty has separate triggers.

### 2. Expiry Day Intelligence
Auto-detects weekly (Thu NIFTY, Tue BNF) and monthly expiry.
- Morning: normal + caution flag
- After 12 PM: targets tightened to 60%, SL 20% tighter
- After 1:30 PM: all new BUY signals blocked (theta decay)
- Banner shows on dashboard

### 3. Signal Accuracy Tracker
Every signal auto-logged with 30m/60m outcome tracking.
Settings page shows win rate, by signal type, by hour, expiry performance.

### 4. Partial Exit (50/25/25)
At T1: exit 50% lots. At T2: exit 25% more. Trail remaining 25%.

### 5. Telegram Bot (Two-Way Interactive)
**Outbound alerts (auto-pushed):**
- 📊 Confluence signals (BUY CE/PE only, skips NO TRADE)
- ⚡ Quick 5-min signals
- 🔮 BTST predictions (3 PM)
- 🟡🟢 Trailing SL stage changes (BREAKEVEN, T1, T2)
- 🛑🎯 SL hits / Target hits
- ⚠️ Expiry day warnings

**Inbound commands (user sends to bot):**
```
/price  /p   — NIFTY & BANKNIFTY live price + VIX
/signal /s   — Latest confluence signal (both symbols)
/quick  /q   — Latest quick 5-min signal
/btst   /b   — BTST prediction + GIFT NIFTY
/vix    /v   — India VIX + zone + analysis
/oi          — PCR, max pain, OI bias
/positions   — Open BTST positions
/pos         — (shortcut for /positions)
/pnl         — P&L summary (wins, losses, total)
/global /g   — Global market score + indices
/news   /n   — Latest headlines with sentiment
/alerts /a   — Active alerts
/levels /l   — CPR + ORB levels
/health      — System status (cache, breakers, LLM)
/help        — Show all commands
```

**Implementation details:**
- Polling-based (3s interval via APScheduler job)
- Config persisted to `/data/telegram_config.json` (survives Railway restarts)
- Auto-loads config on startup via `main.py` lifespan
- Only responds to configured chat_id (security)
- Reads directly from in-memory cache (same real-time data as dashboard)
- Positions/PNL queries use SQLAlchemy directly
- **Settings page CRUD:** Connect, Edit (update token/chat_id), Send Test, Disconnect
- Shows masked token + chat_id when connected
- Disconnect deletes config file and stops all alerts/polling

### 6. Take Trade Button
Signal cards have "TAKE TRADE" button during market hours.
Creates position automatically → monitored with trailing SL.

---

## SCHEDULER JOBS (14 total)

```
# Market Hours Only (signal generation)
job_price_1s          — Live NIFTY/BNF/VIX price (1s)
job_option_ltp_3s     — Option chain LTP (3s)
job_position_monitor_3s — Trailing SL monitor (3s)
job_oi_15s            — OI + PCR (15s)
job_quick_signal_15s  — Quick scalping signals (15s)
job_alerts_15s        — Exit alerts (15s)
job_vix_analysis_60s  — VIX analysis (60s)
job_sentiment_3m      — News sentiment (3m)
job_global_5m         — Global indices (5m)
job_btst_5m           — BTST prediction (5m) — runs after close too
job_vix_history_10m   — VIX history (10m)

# Always-On (runs 24/7)
job_signal_60s        — Indicators computed 24/7, signals only during market hours
job_telegram_poll_3s  — Poll Telegram for commands (3s)

# Daily
job_daily_levels      — CPR/ORB at 9:15 AM IST
```

---

## ENVIRONMENT VARIABLES

```bash
DATABASE_URL=sqlite:///./btst_history.db   # Railway: sqlite:////data/btst_history.db
PORT=8000
CORS_ORIGINS=*
ENABLE_LLM=true
ENABLE_SENTIMENT=true
ENABLE_OPTION_CHAIN=true
LOG_LEVEL=INFO
# NVIDIA_API_KEY not needed in env — stored in SQLite via Settings page
# Telegram bot_token/chat_id — stored in JSON file via Settings page
```

---

## RAILWAY DEPLOYMENT (IMPORTANT)

### Persistent Volume Required
Railway containers are **ephemeral** — filesystem resets on every redeploy.
SQLite DB + Telegram config will be lost without a volume.

**Setup:**
1. Railway Dashboard → your service → Volumes tab
2. Add Volume: mount path = `/data`, size = 1 GB
3. Set env var: `DATABASE_URL=sqlite:////data/btst_history.db`
4. Railway auto-redeploys. Data now persists.

### Custom Domain (for mobile network access)
Indian mobile carriers (Jio, Airtel, Vi) block `*.railway.app` domains.
Fix: Add a custom domain (e.g., `app.niftysignals.in`) in Railway → Networking.

### Deploy Commands
```bash
cd backend
git add . && git commit -m "deploy"
git push origin main

# Railway auto-deploys from GitHub
# Open YOUR-URL/health to verify
```

### Local Development
```bash
cd backend
pip install -r requirements.txt
python main.py
# Open http://localhost:8000
```

---

## COMPLETED SPRINTS

### Sprint 1-3: Backend (FastAPI + WebSocket + SQLite) ✅
All 30 tasks complete. 13 scheduler jobs, 25+ endpoints, 12+ WS events.

### Sprint 4-5: Frontend (React + shadcn/ui) ✅
All 20 tasks complete. 3 pages, 15+ components, system logs panel.

### Sprint 6: BTST History ✅
Stats cards, P&L chart, position table, add/exit dialogs, CSV export, bulk delete.

### Sprint 7: Production Hardening ✅
Error boundaries, circuit breakers, SQLite backup, README.

### Sprint 8: Strategy Upgrades ✅ (Bonus)
Signal engine v3, quick signals v3, sentiment v4, BTST v3.

### Sprint 9: Trade Management ✅ (Bonus)
Trailing SL, expiry day intelligence, signal accuracy, partial exits, Telegram alerts.

### Sprint 10: Production Fixes ✅ (Bonus)
Market closed handling, NaN sanitization, global indices display, GIFT NIFTY proxy,
news REST endpoint, OI REST endpoint, frontend served from backend, Railway deployment.

### Sprint 11: Telegram Interactive Bot + Signal Safety ✅ (Bonus)
- Two-way Telegram bot with 13 commands + shortcuts
- Telegram config persistence (JSON file, survives restarts)
- Auto-load Telegram config on startup
- Telegram poll scheduler job (3s, always-on)
- **BUG FIX:** Removed SELL CE/PE from signal engine (BUY-only now)
- **BUG FIX:** Added market closed guard to confluence signal job
- **BUG FIX:** No more fake signals with garbage Strike:50 Entry:₹50 during weekends

### Sprint 11.1: Indicator Visibility + Telegram CRUD ✅ (Bonus)
- **BUG FIX:** Indicators (RSI, MACD, ADX, Supertrend, etc.) now compute 24/7 — no more infinite loading spinner on dashboard when market is closed. job_signal_60s restructured: indicators + CPR + ORB always computed from yfinance history, only trade signal generation gated to market hours.
- Telegram Settings UI: full CRUD — Connect, Edit (update token/chat_id), Send Test, Disconnect
- Shows masked token + masked chat_id when connected
- New API: `PATCH /api/telegram/configure` (update), `DELETE /api/telegram/configure` (disconnect)
- `disconnect()` method on TelegramService — clears config, deletes JSON file, stops polling
- `GET /api/telegram/status` now returns `token_masked` alongside `chat_id_masked`

---

## REMAINING / FUTURE ENHANCEMENTS

### High Priority (Tier 2)
- [ ] **IV Rank / IV Percentile** — Track VIX percentile over 1 year to decide buy vs sell strategy. When IV rank > 80%, suggest selling; when < 20%, suggest buying.
- [ ] **Multi-timeframe confirmation** — Check if 5m signal aligns with 15m and 1h trend. Require 2/3 timeframes agree before signal fires.
- [ ] **AI Trade Journal** — Weekly LLM analysis of closed trades to find patterns ("you lose on BANKNIFTY PE after 2 PM", "Thursday trades have 23% win rate").
- [ ] **Signal outcome checker job** — Background job that checks signal premium at 30min/60min after signal and updates SignalLog outcome field.

### Medium Priority (Tier 3)
- [ ] **Kelly Criterion position sizing** — Math-optimal bet size based on historical win rate and average win/loss.
- [ ] **Bull/Bear spread suggestions** — Instead of naked CE/PE, suggest spreads (buy ATM + sell OTM) when VIX is high.
- [ ] **NSE holiday calendar** — Hardcoded 2026-2027 NSE holidays for accurate gap day detection.
- [ ] **Weekly P&L dashboard** — Equity curve chart, max drawdown, Sharpe ratio, calendar heatmap.
- [ ] **Candlestick chart** — TradingView Lightweight Charts for OHLCV visualization.

### Low Priority (Nice to Have)
- [ ] **Redis cache** — Replace in-memory dict for multi-instance scaling.
- [ ] **GIFT NIFTY live feed** — If a free API for GIFT NIFTY becomes available, replace the proxy.
- [ ] **Mobile PWA** — Service worker for offline access + push notifications.
- [ ] **Backtesting engine** — Test signal strategies against historical data.
- [ ] **Options Greeks** — Delta/Gamma/Theta/Vega display for selected strikes.
- [ ] **Dark/Light theme toggle** — Currently dark only.

---

## CRITICAL RULES (For future development)

1. **option_type and entry_premium are ALWAYS separate fields.** Never combine as "CE 142.5".
2. **APScheduler jobs use `asyncio.run()` wrapper** — not `get_event_loop()`.
3. **All endpoints return 200 with defaults** — never 404 for missing cache data.
4. **NaN sanitization required** — numpy float64 NaN crashes JSON. Use `_sanitize()`.
5. **Weekend/market-closed signals say "MARKET CLOSED"** — never show false BUY/SELL.
6. **Frontend is bundled in `static/index.html`** — served by FastAPI at `/`.
7. **API calls use relative URLs** (`/api/price`, not `http://localhost:8000/api/price`).
8. **WebSocket URL auto-detected from `location.origin`** — no hardcoded backend URL.
9. **SQLite path**: local = `./btst_history.db`, Railway with volume = `/data/btst_history.db`.
10. **BTST job runs outside market hours** — needed for post-close prediction accuracy.
11. **NEVER generate SELL CE or SELL PE.** This app is BUY-only. Naked selling = unlimited risk.
12. **Signal labels vs actions:** "SELL" label = bearish direction → `BUY PE`. "BUY" label = bullish → `BUY CE`.
13. **Telegram config is in JSON file** (`/data/telegram_config.json`), NOT in SQLite. Auto-loaded on startup.
14. **Railway needs a persistent volume at `/data`** — without it, DB + Telegram config reset on every redeploy.
15. **Indicators compute 24/7.** job_signal_60s always fetches OHLCV + computes indicators + CPR + ORB from yfinance history. Only confluence scoring + trade generation is gated to market hours. This ensures the INDICATORS panel on the dashboard never shows an infinite loading spinner.
16. **Telegram CRUD:** Configure (POST), Update (PATCH), Disconnect (DELETE). The `disconnect()` method clears in-memory config AND deletes the JSON file.
