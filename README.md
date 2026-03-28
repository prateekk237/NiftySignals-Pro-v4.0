# NiftySignals Pro v4.0 — Backend

Real-time Indian F&O trading signal API. FastAPI + WebSocket + SQLite.

## Quick Start

```bash
cd backend
pip install -r requirements.txt
python main.py
# → http://localhost:8000/health
# → WebSocket at ws://localhost:8000/socket.io/
```

## Architecture

```
FastAPI (uvicorn) + python-socketio
├── APScheduler (13 background jobs at 1s → daily intervals)
├── In-memory Cache (TTL per key)
├── SQLite (BTST positions + API keys)
├── WebSocket (12+ event types, push to all clients)
└── REST API (26+ endpoints, reads from cache)
```

## API Endpoints

### Market Data (from cache)
- `GET /api/price?symbol=NIFTY50` — Live price
- `GET /api/vix` — India VIX + analysis
- `GET /api/option-chain?symbol=NIFTY50` — OI data
- `GET /api/strikes?symbol=NIFTY50&type=CE` — Available strikes
- `GET /api/candles?symbol=NIFTY50&interval=15m` — OHLCV for charts
- `GET /api/global` — Global markets score
- `GET /api/indicators?symbol=NIFTY50` — All indicator signals
- `GET /api/levels?symbol=NIFTY50` — CPR + ORB levels

### Signals (from cache)
- `GET /api/signal?symbol=NIFTY50` — Confluence signal
- `GET /api/quick-signal?symbol=NIFTY50` — 5-min scalping
- `GET /api/btst?symbol=NIFTY50` — Gap prediction
- `GET /api/alerts?symbol=NIFTY50` — Real-time alerts

### BTST Positions (SQLite)
- `GET /api/positions` — List all
- `GET /api/positions/open` — Open only
- `GET /api/positions/stats` — Win rate, P&L stats
- `POST /api/positions` — Add position
- `PATCH /api/positions/{id}/exit` — Close with exit premium
- `DELETE /api/positions/{id}` — Delete
- `POST /api/positions/bulk-delete` — Bulk delete
- `GET /api/positions/export/csv` — CSV export
- `GET /api/positions/gap-check` — Gap day warning

### API Keys (SQLite, persistent)
- `GET /api/keys` — List keys (masked)
- `POST /api/keys` — Add key
- `PATCH /api/keys/{id}` — Update
- `DELETE /api/keys/{id}` — Delete
- `POST /api/keys/test` — Test before saving
- `POST /api/keys/reload` — Reload into LLM service

### System
- `GET /health` — Full health check
- `GET /api/system/circuit-breakers` — Breaker status
- `POST /api/system/backup` — SQLite backup
- `GET /api/system/backup/download` — Download DB
- `POST /api/system/cache/clear` — Clear cache

## WebSocket Events

| Event | Interval | Description |
|-------|----------|-------------|
| `price_update` | 1s | Live spot price + VIX |
| `option_ltp_update` | 3s | ATM CE/PE LTPs |
| `oi_update` | 15s | OI analysis + PCR |
| `quick_signal_update` | 15s | 5-min scalping signal |
| `alert_update` | 15s | Exit alerts |
| `signal_update` | 60s | Confluence signal |
| `vix_analysis_update` | 60s | VIX zone + trend |
| `news_update` | 3m | Sentiment + headlines |
| `global_update` | 5m | Global markets |
| `btst_update` | 5m | Gap prediction |
| `btst_sl_alert` | On trigger | SL hit alert |
| `btst_target_alert` | On trigger | Target hit alert |

## Deploy to Railway

```bash
# Set environment variables in Railway dashboard:
# NVIDIA_API_KEY, DATABASE_URL, CORS_ORIGINS, PORT
railway up
```

## LLM Fallback Chain

Keys are stored in SQLite. The system tries each provider in priority order:
1. NVIDIA NIM (Llama 3.3 70B, free tier)
2. OpenAI (GPT-4o, pay-per-use)
3. Any OpenAI-compatible (Ollama, Groq, Together, etc.)
4. VADER (offline, no API needed)
