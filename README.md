# APEX AI Paper Trading Agent

APEX is a full-stack paper-trading app for Indian equities.

- Backend: FastAPI + SQLite + OpenAI + yfinance
- Frontend: React + Vite + Tailwind CSS
- Currency: INR (Rs)
- Trading mode: Paper only (no real broker orders)

## What This Project Does

- Lets you configure trading behavior from the Settings page
- Scans selected Indian stock universe (Nifty/Sensex groups)
- Gets market indicators (price, RSI, MA20, MA50)
- Uses AI + rule engine to decide BUY/SELL/HOLD
- Executes virtual trades in a paper wallet
- Tracks open positions, unrealized PnL, and trade history
- Supports auto-trading loop (start/stop)

## Important Reality About "Tick to Tick" Free Data

Free Yahoo/yfinance data is useful for paper trading, but it is not guaranteed true exchange tick-by-tick feed.

- Data may be delayed or missing for some symbols at times
- Some intervals can fail during rate limits or market session changes
- For strict production-grade low-latency execution, paid broker/exchange feeds are needed

This app includes fallbacks to reduce missing price issues, but free data still has limits.

## Project Structure

```text
apex-trading-zip/
  backend/
    app.py                # FastAPI routes and auto-trading loop
    ai_agent.py           # OpenAI decision call
    trading_engine.py     # Paper trade execution and position state
    market_data.py        # Quotes and indicators from Yahoo/yfinance
    live_data_service.py  # 5d/1m live data fetch helper
    stock_universes.py    # Nifty/Sensex stock lists
    settings.py           # Settings defaults/load/save
    settings.json         # Runtime settings persisted here
    database.py           # SQLite tables + CRUD
    trades.db             # SQLite DB (auto-created)
    requirements.txt
  frontend/
    src/
      pages/              # Dashboard, Wallet, History, Settings
      components/         # Navbar, Chart, Card, Spinner
      api.js              # Axios API wrapper
  start.bat
  start.sh
  README.md
```

## Requirements

- Python 3.10+
- Node.js 18+
- npm

## Quick Start

### 1) Configure backend environment

Copy `backend/.env.example` to `backend/.env` and set:

```env
OPENAI_API_KEY=your_key_here
APEX_API_TOKEN=your_strong_random_token   # optional but recommended
```

If `APEX_API_TOKEN` is set, mutating API routes require either:
- `x-api-key: <token>` header, or
- `Authorization: Bearer <token>`

### 2) Start backend

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8000
```

### 3) Configure frontend environment

Copy `frontend/.env.example` to `frontend/.env` and set:

```env
VITE_API_URL=http://localhost:8000
VITE_API_TOKEN=your_strong_random_token
```

Leave `VITE_API_TOKEN` empty only if you intentionally run backend without `APEX_API_TOKEN`.

### 4) Start frontend

```bash
cd frontend
npm install
npm run dev
```

### 5) Open app

- Frontend: `http://localhost:3000`
- Backend docs (Swagger): `http://localhost:8000/docs`

## Windows One-Click Start

`start.bat` will:

1. Install backend dependencies
2. Install frontend dependencies (if needed)
3. Open backend and frontend in separate terminals

`start.bat` / `start.sh` bind backend to `127.0.0.1` by default for safer local use.

## Trading Universes Supported

Configured in `backend/stock_universes.py`:

- Nifty 50
- S&P BSE Sensex
- Nifty Bank
- Nifty Next 50
- Nifty 100

Crypto is removed in current flow.

## Core Backend Behavior

### Trading flow

1. Load settings
2. Resolve selected stock universe
3. Pull indicators for each stock
4. Apply entry filters (RSI, price, volume, trend)
5. Ask AI for decision (or force risk-exit if position is wrong)
6. Apply rule-engine constraints (confidence, RR, loss limits, cooldown, max positions)
7. Execute paper trade in `trading_engine.py`
8. Record trade + rule log
9. Recompute portfolio using latest quotes

### Day-trade short selling

- In `day_trade` style, SELL can open short when flat
- BUY can cover short
- Unrealized and realized PnL are handled in wallet math

### Auto-trading safety

- Auto-trade continues until explicitly stopped
- If `auto_start` is enabled, backend restart resumes auto-trading automatically
- Auto-trade can be stopped anytime from UI or API

## Settings Explained (Field by Field)

These are persisted in `backend/settings.json`.

- `stock_universe`: Which index basket to scan
- `style`: `day_trade`, `short_term`, `long_term`
- `risk`: `low`, `medium`, `high`
- `trade_amount`: Default per-trade notional in INR
- `risk_per_trade_pct`: Caps trade notional using wallet risk budget
- `min_confidence`: Minimum AI confidence for new entries
- `max_daily_loss_pct`: Blocks new entries after daily drawdown breach
- `max_open_positions`: Maximum simultaneous open positions
- `max_trades_per_day`: Entry cap per day
- `loss_streak_cooldown`: Loss streak threshold to trigger cooldown
- `cooldown_minutes`: Cooldown duration after streak trigger
- `stop_loss_pct`: Stop-loss percentage
- `take_profit_pct`: Take-profit percentage
- `min_rr`: Minimum risk/reward required for entries
- `max_holding_minutes_day_trade`: Time-based exit limit for day trade
- `no_averaging_down`: Prevent adding to losing position
- `rsi_min`, `rsi_max`: RSI filter window
- `min_price`, `max_price`: Price band filter
- `min_volume`: Minimum average volume filter
- `require_uptrend`: Requires MA20 > MA50 for entries
- `auto_start`: Auto-loop state toggle
- `loop_interval_seconds`: Auto-loop cycle interval (5-300)
- `execution_slippage_bps`: Simulated adverse fill slippage in basis points
- `brokerage_fee_bps`: Simulated proportional brokerage/fees in basis points
- `fixed_fee_per_order`: Simulated flat fee per filled order

## API Endpoints

Base URL: `http://localhost:8000`

### Health

- `GET /`
- `GET /healthz` (liveness probe)
- `GET /readyz` (readiness probe, returns 503 if critical deps are missing)

### Trading

- `POST /run` (scan full selected universe)
- `POST /run?asset=RELIANCE.NS` (run one asset)
- `POST /autotrade/start`
- `POST /autotrade/stop`
- `GET /autotrade/status`

### Portfolio and logs

- `GET /portfolio`
- `GET /history?limit=50`
- `GET /rule-logs?limit=100`
- `GET /performance/report?limit=1000`
  - Includes aggregate metrics and `daily_realized_last_7d` trend data
- `POST /reset`

### Market data

- `GET /quotes` (selected universe quotes)
- `GET /quotes?assets=RELIANCE.NS,TCS.NS`
- `POST /market/live-data`

Example request for `/market/live-data`:

```json
{
  "symbols": ["RELIANCE", "TCS"],
  "exchange": "NSE",
  "retries": 3,
  "include_history": true
}
```

### Settings and universes

- `GET /settings`
- `PATCH /settings`
- `GET /universes`

## Frontend Pages

- `/` Dashboard
  - Run cycle
  - Start/stop auto trade
  - Live price card
  - Equity and PnL summary
  - Open positions
- `/wallet`
  - Cash, equity, PnL, trade count
  - Open positions table
  - Wallet reset
- `/history`
  - Trade history
  - Realized and live PnL snapshots
  - Rule engine logs
- `/settings`
  - Universe, strategy, risk, filters, loop controls

## Troubleshooting

### "uvicorn is not recognized"

Use module mode:

```bash
python -m uvicorn app:app --reload --port 8000
```

### Backend unreachable from frontend

- Ensure backend is running on `localhost:8000`
- Ensure frontend runs on `localhost:3000`

### OpenAI key error

- Confirm `backend/.env` exists
- Confirm `OPENAI_API_KEY` is valid
- Restart backend after updating `.env`

### Some symbols show no live price

- Free Yahoo feed can be intermittent
- App uses fallbacks, but occasional gaps are still possible
- Retry after a short wait, especially near market open/close or rate limits

### History/Wallet stuck loading

- Check backend terminal for errors
- Verify `trades.db` is writable
- Restart backend and refresh frontend

## Deployment Notes

### Backend on Render

This repo includes `render.yaml` for the backend service.

1. Push repository to GitHub.
2. In Render, create a **Blueprint** from the repo (it reads `render.yaml`), or create a Web Service manually using:
   - Root directory: `backend`
   - Build command: `pip install -r requirements.txt`
   - Start command: `python -m uvicorn app:app --host 0.0.0.0 --port $PORT`
3. Add a **Persistent Disk** and mount it at `/var/data`.
4. Set backend environment variables:
   - `OPENAI_API_KEY=<your_key>`
   - `APEX_API_TOKEN=<strong_random_token>`
   - `CORS_ORIGINS=https://<your-vercel-domain>.vercel.app`
   - `TRADES_DB_PATH=/var/data/trades.db`
5. Verify health endpoints:
   - `/healthz`
   - `/readyz`

### Frontend on Vercel

Deploy `frontend/` as a Vite app (this repo includes `frontend/vercel.json` for SPA routing).

Set Vercel environment variables:

- `VITE_API_URL=https://<your-render-backend>.onrender.com`
- `VITE_API_TOKEN=<same_value_as_APEX_API_TOKEN>`

After deploy:

1. Open frontend URL.
2. Check Dashboard loads portfolio/quotes.
3. Use Settings to start auto-trade.
4. Confirm backend `/autotrade/status` shows `running: true`.

## Security and Risk Notes

- Never commit real API secrets to git
- Use `backend/.env.example` and `frontend/.env.example` as templates; keep real `.env` files local only
- Set `APEX_API_TOKEN` in backend and `VITE_API_TOKEN` in frontend to protect mutating API routes
- Keep testing in paper mode with realistic costs (`execution_slippage_bps`, `brokerage_fee_bps`, `fixed_fee_per_order`)
- Keep this in paper mode unless broker integration is reviewed carefully
- AI decisions are probabilistic and can be wrong
- Add strong risk controls before any live-money extension

## Disclaimer

This software is for educational and simulation purposes only.
It is not financial advice.
