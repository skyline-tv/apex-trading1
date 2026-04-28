"""
GenAI Paper Trading Agent - FastAPI entry-point.

Run:
    python -m uvicorn app:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from threading import Event, Lock, Thread
from typing import Optional
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database
import settings as settings_module
from market_data import fetch_indicators, fetch_live_quotes, fetch_bulk_last_close
from ai_agent import get_trading_decision
from trading_engine import STARTING_BALANCE, get_engine
from stock_universes import UNIVERSE_ASSETS, UNIVERSE_LABELS
from live_data_service import fetch_live_market_data
from market_hours import nse_regular_session_status

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)
API_AUTH_TOKEN = os.getenv("APEX_API_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

database.init_db()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup: resume auto-trade if enabled. Shutdown: stop the loop."""
    logger.info("Server starting up.")
    _stop_auto_loop()
    try:
        cfg = settings_module.load_settings()
        if cfg.get("auto_start", False):
            started = _start_auto_loop_if_needed(force=False)
            logger.info("Auto-trade resume requested at startup (started=%s).", started)
    except Exception as exc:
        logger.exception("Failed to evaluate auto-trade startup state: %s", exc)
    yield
    logger.info("Server shutting down — stopping auto-trade loop.")
    _stop_auto_loop()


app = FastAPI(
    title="GenAI Paper Trading Agent",
    description="AI-powered paper trading using OpenAI + yfinance",
    version="1.5.0",
    lifespan=lifespan,
)

_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not API_AUTH_TOKEN:
    logger.warning("APEX_API_TOKEN is not set; mutating API routes are currently unprotected.")

# ---------------------------------------------------------------------------
# Auto-trading loop state
# ---------------------------------------------------------------------------

DEFAULT_LOOP_INTERVAL_SEC = 20

_loop_thread: Thread | None = None
_loop_stop = Event()
_loop_lock = Lock()
_loop_running = False
_loop_last_error = ""
_loop_last_run_at = ""

CANONICAL_UNIVERSES = ["nifty_50", "sensex", "nifty_bank", "nifty_next_50", "nifty_100"]
UNIVERSE_ALIASES = {"bse_50": "sensex"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SettingsUpdate(BaseModel):
    market: Optional[str] = None
    stock_universe: Optional[str] = None
    style: Optional[str] = None
    risk: Optional[str] = None
    trade_amount: Optional[float] = None
    risk_per_trade_pct: Optional[float] = None
    min_confidence: Optional[int] = None
    max_daily_loss_pct: Optional[float] = None
    max_open_positions: Optional[int] = None
    max_trades_per_day: Optional[int] = None
    loss_streak_cooldown: Optional[int] = None
    cooldown_minutes: Optional[int] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    min_rr: Optional[float] = None
    max_holding_minutes_day_trade: Optional[int] = None
    no_averaging_down: Optional[bool] = None
    rsi_min: Optional[float] = None
    rsi_max: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_volume: Optional[float] = None
    require_uptrend: Optional[bool] = None
    auto_start: Optional[bool] = None
    respect_market_hours: Optional[bool] = None
    loop_interval_seconds: Optional[int] = None
    execution_slippage_bps: Optional[float] = None
    brokerage_fee_bps: Optional[float] = None
    fixed_fee_per_order: Optional[float] = None
    watchlist_only: Optional[bool] = None
    max_symbols_per_cycle: Optional[int] = None
    require_fresh_indicators: Optional[bool] = None


class LiveDataRequest(BaseModel):
    symbols: list[str]
    exchange: str = "NSE"
    retries: int = 3
    include_history: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_universe_key(cfg: dict) -> str:
    raw = str(cfg.get("stock_universe", "nifty_50")).strip().lower()
    raw = UNIVERSE_ALIASES.get(raw, raw)
    return raw if raw in UNIVERSE_ASSETS else "nifty_50"


def _resolve_assets(cfg: dict) -> list[str]:
    return list(UNIVERSE_ASSETS[_resolve_universe_key(cfg)])


def _select_cycle_assets(cfg: dict) -> list[str]:
    """
    Symbols scanned in one universe cycle: optional watchlist ∩ universe,
    then optional daily rotation cap (saves data + OpenAI costs).
    """
    full = _resolve_assets(cfg)
    allowed_set = set(full)
    if bool(cfg.get("watchlist_only")):
        wl: list[str] = []
        for a in cfg.get("assets") or []:
            u = str(a).upper().strip()
            if u and u in allowed_set:
                wl.append(u)
        full = wl
    max_n = int(cfg.get("max_symbols_per_cycle") or 0)
    if max_n <= 0 or len(full) <= max_n:
        return full
    shift = date.today().toordinal() % len(full)
    rotated = full[shift:] + full[:shift]
    return rotated[:max_n]


def _indicators_stale_reason(indicators: dict, cfg: dict, interval: str) -> str | None:
    """Return a human reason if bar timestamps are too old for the bar interval."""
    if not bool(cfg.get("require_fresh_indicators", True)):
        return None
    as_of_s = indicators.get("as_of")
    if not as_of_s:
        return None
    try:
        raw = str(as_of_s).replace("Z", "+00:00")
        as_of = datetime.fromisoformat(raw)
    except Exception:
        return None
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - as_of
    interval = (interval or "").lower()
    intraday = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "240m", "4h"}
    if interval in intraday:
        if age > timedelta(hours=6):
            return f"Stale intraday bars (last bar {as_of_s}, age {age})."
    elif interval in ("1d", "1wk", "1mo", "3mo"):
        if interval == "1d" and age > timedelta(days=7):
            return f"Stale daily bars (last bar {as_of_s})."
        if interval != "1d" and age > timedelta(days=21):
            return f"Stale indicator data (last bar {as_of_s})."
    else:
        if age > timedelta(days=14):
            return f"Stale indicator data (last bar {as_of_s})."
    return None


def _asset_is_allowed(asset: str, cfg: dict) -> bool:
    return asset.upper().strip() in set(_resolve_assets(cfg))


def _session_allows_trading(cfg: dict) -> tuple[bool, str]:
    """When True, run cycles may fetch data and execute paper trades."""
    if not bool(cfg.get("respect_market_hours", True)):
        return True, ""
    market = str(cfg.get("market", "indian_stocks")).lower().strip()
    if market != "indian_stocks":
        return True, ""
    return nse_regular_session_status()


def _get_loop_interval_seconds(cfg: dict) -> int:
    raw = cfg.get("loop_interval_seconds", DEFAULT_LOOP_INTERVAL_SEC)
    try:
        value = int(raw)
    except Exception:
        value = DEFAULT_LOOP_INTERVAL_SEC
    return max(5, min(300, value))


def _get_indicator_window(style: str) -> tuple[str, str]:
    style_norm = (style or "short_term").lower().strip()
    if style_norm == "day_trade":
        return ("5d", "1m")
    if style_norm == "long_term":
        return ("1y", "1d")
    return ("1mo", "5m")


def _get_stop_loss_pct(cfg: dict) -> float:
    """Risk-tier stop threshold for forced exit logic."""
    risk = str(cfg.get("risk", "medium")).lower().strip()
    if risk == "low":
        return 0.008   # 0.8%
    if risk == "high":
        return 0.025   # 2.5%
    return 0.015       # 1.5%


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_trade_time(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _extract_bearer_token(authorization: Optional[str]) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts[0].lower(), parts[1].strip()
    if scheme != "bearer" or not token:
        return None
    return token


def _require_api_token(
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """
    Protect mutating endpoints when APEX_API_TOKEN is configured.
    """
    if not API_AUTH_TOKEN:
        return
    candidate = (x_api_key or _extract_bearer_token(authorization) or "").strip()
    if len(candidate) != len(API_AUTH_TOKEN) or not secrets.compare_digest(
        candidate, API_AUTH_TOKEN
    ):
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing API token.")


# Per-cycle cache for daily trade stats: avoids N×5000-row DB reads per universe scan.
_stats_cache: dict | None = None
_stats_cache_ts: float = 0.0
_STATS_CACHE_TTL: float = 15.0  # seconds


def _daily_trade_stats(force_refresh: bool = False) -> dict:
    global _stats_cache, _stats_cache_ts
    now_ts = time.time()
    if not force_refresh and _stats_cache is not None and (now_ts - _stats_cache_ts) < _STATS_CACHE_TTL:
        return _stats_cache

    trades = database.get_trades(limit=5000)
    today = _utc_now().date()
    today_trades = []
    for t in trades:
        dt = _parse_trade_time(str(t.get("timestamp", "")))
        if dt and dt.date() == today:
            today_trades.append(t)

    realized_pnl = sum(float(t.get("profit") or 0.0) for t in today_trades)
    consecutive_losses = 0
    # get_trades returns latest first; count latest loss streak.
    for t in today_trades:
        profit = float(t.get("profit") or 0.0)
        if profit < 0:
            consecutive_losses += 1
        else:
            break
    last_ts = None
    if today_trades:
        last_ts = _parse_trade_time(str(today_trades[0].get("timestamp", "")))

    result = {
        "count": len(today_trades),
        "realized_pnl": realized_pnl,
        "consecutive_losses": consecutive_losses,
        "last_trade_at": last_ts,
    }
    _stats_cache = result
    _stats_cache_ts = now_ts
    return result


def _count_open_positions(engine) -> int:
    return sum(1 for _a, p in engine.get_position_details().items() if abs(float(p.get("quantity", 0.0))) > 0)


def _classify_action(side: str | None, decision: str, allow_short: bool) -> str:
    side = (side or "").upper()
    decision = (decision or "").upper()
    if decision not in {"BUY", "SELL"}:
        return "none"
    if not side:
        if decision == "BUY":
            return "open_long"
        if decision == "SELL" and allow_short:
            return "open_short"
        return "invalid"
    if side == "LONG":
        return "close_long" if decision == "SELL" else "add_long"
    if side == "SHORT":
        return "close_short" if decision == "BUY" else "add_short"
    return "invalid"


def _calc_trade_notional(cfg: dict, wallet_balance: float) -> float:
    base = float(cfg.get("trade_amount", 10_000))
    risk_pct = float(cfg.get("risk_per_trade_pct", 0.01))
    risk_cap = max(100.0, wallet_balance * max(0.001, min(0.2, risk_pct)))
    return max(100.0, min(base, risk_cap))


def _log_rule_event(
    asset: str,
    event_type: str,
    decision: str | None,
    reason: str,
    source: str = "manual",
    confidence: int | None = None,
):
    try:
        database.record_rule_log(
            asset=asset,
            event_type=event_type,
            decision=decision,
            reason=reason,
            source=source,
            confidence=confidence,
        )
    except Exception:
        # Logging must never block trading flow.
        pass


def _enforce_rule_engine(
    cfg: dict,
    indicators: dict,
    current_pos: dict | None,
    ai_result: dict,
    wallet_balance: float,
    open_positions: int,
) -> tuple[dict, str | None]:
    """
    Returns (possibly modified decision payload, block_reason).
    If block_reason is not None, caller should skip execution.
    """
    decision = str(ai_result.get("decision", "HOLD")).upper()
    confidence = int(ai_result.get("confidence", 50))
    side = (current_pos.get("side") if current_pos else None)
    allow_short = str(cfg.get("style", "")).lower() == "day_trade"
    action = _classify_action(side, decision, allow_short)
    if action == "invalid":
        return ai_result, "Action invalid for current position/style"

    stats = _daily_trade_stats()
    daily_loss_limit = STARTING_BALANCE * float(cfg.get("max_daily_loss_pct", 0.03))
    if stats["realized_pnl"] <= -abs(daily_loss_limit) and action.startswith("open"):
        return ai_result, "Daily loss limit reached; new entries blocked."

    max_trades_day = int(cfg.get("max_trades_per_day", 30))
    if stats["count"] >= max_trades_day and action.startswith("open"):
        return ai_result, "Max trades per day reached; new entries blocked."

    streak_limit = int(cfg.get("loss_streak_cooldown", 3))
    cooldown_min = int(cfg.get("cooldown_minutes", 30))
    if (
        stats["consecutive_losses"] >= streak_limit
        and stats["last_trade_at"] is not None
        and _utc_now() < (stats["last_trade_at"] + timedelta(minutes=cooldown_min))
        and action.startswith("open")
    ):
        return ai_result, "Cooldown active after loss streak; new entries blocked."

    if confidence < int(cfg.get("min_confidence", 60)) and action.startswith("open"):
        return ai_result, f"Confidence {confidence}% below minimum threshold."

    rr = float(cfg.get("take_profit_pct", 0.03)) / max(0.0001, float(cfg.get("stop_loss_pct", _get_stop_loss_pct(cfg))))
    if rr < float(cfg.get("min_rr", 1.5)) and action.startswith("open"):
        return ai_result, f"Risk/reward {rr:.2f} below minimum."

    ma20 = float(indicators.get("ma20", 0.0))
    ma50 = float(indicators.get("ma50", 0.0))
    if action in {"open_long", "add_long"} and ma20 < ma50:
        return ai_result, "Trend misaligned for long entry (MA20 < MA50)."
    if action in {"open_short", "add_short"} and ma20 > ma50:
        return ai_result, "Trend misaligned for short entry (MA20 > MA50)."

    if action.startswith("open") and open_positions >= int(cfg.get("max_open_positions", 8)):
        return ai_result, "Max open positions reached."

    if bool(cfg.get("no_averaging_down", True)) and current_pos and action in {"add_long", "add_short"}:
        avg_cost = float(current_pos.get("avg_cost", 0.0))
        px = float(indicators.get("price", 0.0))
        if avg_cost > 0 and px > 0:
            if side == "LONG" and px < avg_cost:
                return ai_result, "No averaging down: LONG is under water."
            if side == "SHORT" and px > avg_cost:
                return ai_result, "No averaging down: SHORT is under water."

    # Clip notional by risk budget for opening/add actions.
    if action in {"open_long", "open_short", "add_long", "add_short"}:
        ai_result["_trade_notional"] = _calc_trade_notional(cfg, wallet_balance)
    else:
        ai_result["_trade_notional"] = float(cfg.get("trade_amount", 10_000))

    return ai_result, None


def _approx_position_age_minutes(asset: str, side: str) -> float | None:
    """
    Approximate open position age using the most recent trade in the same direction.
    """
    decision = "BUY" if side == "LONG" else "SELL"
    trades = database.get_trades(limit=5000)
    for t in trades:
        if str(t.get("asset", "")).upper() != asset.upper():
            continue
        if str(t.get("decision", "")).upper() != decision:
            continue
        dt = _parse_trade_time(str(t.get("timestamp", "")))
        if not dt:
            return None
        delta = _utc_now() - dt
        return max(0.0, delta.total_seconds() / 60.0)
    return None


def _forced_exit_decision(indicators: dict, position: dict, cfg: dict, asset: str) -> dict | None:
    """
    Force-close a position when trade is clearly going wrong.
    Returns a decision payload compatible with AI output, or None.
    """
    side = str(position.get("side", "")).upper()
    avg_cost = float(position.get("avg_cost", 0.0))
    price = float(indicators.get("price", 0.0))
    ma20 = float(indicators.get("ma20", 0.0))
    ma50 = float(indicators.get("ma50", 0.0))
    rsi = float(indicators.get("rsi", 50.0))
    if avg_cost <= 0 or price <= 0:
        return None

    stop_pct = _get_stop_loss_pct(cfg)
    take_profit_pct = float(cfg.get("take_profit_pct", 0.03))
    age_min = _approx_position_age_minutes(asset, side)
    max_hold_day_trade = int(cfg.get("max_holding_minutes_day_trade", 180))

    if side == "LONG":
        drawdown = (price - avg_cost) / avg_cost
        if drawdown <= -stop_pct:
            return {
                "decision": "SELL",
                "confidence": 95,
                "reason": f"Risk exit: LONG stop-loss hit ({drawdown * 100:.2f}%).",
            }
        if ma20 < ma50 and rsi < 45:
            return {
                "decision": "SELL",
                "confidence": 88,
                "reason": "Risk exit: trend reversed against LONG (MA20<MA50, RSI weak).",
            }
        if drawdown >= take_profit_pct:
            return {
                "decision": "SELL",
                "confidence": 85,
                "reason": f"Discipline exit: LONG take-profit hit ({drawdown * 100:.2f}%).",
            }
        if str(cfg.get("style", "")).lower() == "day_trade" and age_min is not None and age_min >= max_hold_day_trade:
            return {
                "decision": "SELL",
                "confidence": 80,
                "reason": f"Time exit: LONG exceeded max hold ({int(age_min)}m).",
            }
    elif side == "SHORT":
        adverse = (avg_cost - price) / avg_cost
        if adverse <= -stop_pct:
            return {
                "decision": "BUY",
                "confidence": 95,
                "reason": f"Risk exit: SHORT stop-loss hit ({adverse * 100:.2f}%).",
            }
        if ma20 > ma50 and rsi > 55:
            return {
                "decision": "BUY",
                "confidence": 88,
                "reason": "Risk exit: trend reversed against SHORT (MA20>MA50, RSI strong).",
            }
        if adverse >= take_profit_pct:
            return {
                "decision": "BUY",
                "confidence": 85,
                "reason": f"Discipline exit: SHORT take-profit hit ({adverse * 100:.2f}%).",
            }
        if str(cfg.get("style", "")).lower() == "day_trade" and age_min is not None and age_min >= max_hold_day_trade:
            return {
                "decision": "BUY",
                "confidence": 80,
                "reason": f"Time exit: SHORT exceeded max hold ({int(age_min)}m).",
            }
    return None


def _filter_reasons(indicators: dict, cfg: dict) -> list[str]:
    reasons: list[str] = []
    price = float(indicators.get("price", 0.0))
    rsi = float(indicators.get("rsi", 0.0))
    ma20 = float(indicators.get("ma20", 0.0))
    ma50 = float(indicators.get("ma50", 0.0))
    avg_volume = float(indicators.get("avg_volume_20", 0.0))

    if price < float(cfg.get("min_price", 0.0)):
        reasons.append(f"price {price:.2f} < min_price")
    if price > float(cfg.get("max_price", 1_000_000.0)):
        reasons.append(f"price {price:.2f} > max_price")
    if rsi < float(cfg.get("rsi_min", 0.0)):
        reasons.append(f"rsi {rsi:.2f} < rsi_min")
    if rsi > float(cfg.get("rsi_max", 100.0)):
        reasons.append(f"rsi {rsi:.2f} > rsi_max")
    if avg_volume < float(cfg.get("min_volume", 0.0)):
        reasons.append(f"avg_volume {avg_volume:.0f} < min_volume")
    if bool(cfg.get("require_uptrend", False)) and ma20 < ma50:
        reasons.append("ma20 < ma50 (uptrend required)")

    return reasons


def _run_one_asset(cfg: dict, asset: str, source: str = "manual") -> dict:
    target_asset = asset.upper().strip()
    if not _asset_is_allowed(target_asset, cfg):
        reason = "Asset is not in selected stock universe."
        _log_rule_event(target_asset, "universe_reject", "SKIP", reason, source=source)
        return {
            "asset": target_asset,
            "decision": "SKIP",
            "skipped": True,
            "skip_reason": reason,
            "run_source": source,
        }

    allowed, session_reason = _session_allows_trading(cfg)
    if not allowed:
        _log_rule_event(
            target_asset,
            "session_closed",
            "SKIP",
            session_reason,
            source=source,
        )
        return {
            "asset": target_asset,
            "decision": "SKIP",
            "skipped": True,
            "skip_reason": session_reason,
            "run_source": source,
        }

    period, interval = _get_indicator_window(cfg.get("style", "short_term"))

    try:
        indicators = fetch_indicators(target_asset, period=period, interval=interval)
    except Exception as exc:
        reason = f"Market data error: {exc}"
        _log_rule_event(target_asset, "data_error", "SKIP", reason, source=source)
        return {
            "asset": target_asset,
            "decision": "SKIP",
            "skipped": True,
            "skip_reason": reason,
            "run_source": source,
        }

    stale_reason = _indicators_stale_reason(indicators, cfg, interval)
    if stale_reason:
        _log_rule_event(target_asset, "stale_data", "SKIP", stale_reason, source=source)
        return {
            "asset": target_asset,
            "decision": "SKIP",
            "skipped": True,
            "skip_reason": stale_reason,
            "indicators": indicators,
            "run_source": source,
        }

    engine = get_engine()
    current_pos = engine.get_position_details().get(target_asset)

    # Entry filters apply only when we are flat on this asset.
    if not current_pos:
        reasons = _filter_reasons(indicators, cfg)
        if reasons:
            reason = "; ".join(reasons)
            _log_rule_event(target_asset, "filter_block", "SKIP", reason, source=source)
            return {
                "asset": target_asset,
                "decision": "SKIP",
                "skipped": True,
                "skip_reason": reason,
                "indicators": indicators,
                "run_source": source,
            }

    # Hard risk controls: force exit if position is clearly wrong.
    forced = None
    if current_pos:
        forced = _forced_exit_decision(indicators, current_pos, cfg, target_asset)
        if forced:
            _log_rule_event(
                target_asset,
                "forced_exit",
                forced.get("decision"),
                forced.get("reason", ""),
                source=source,
                confidence=int(forced.get("confidence", 0)),
            )

    try:
        if forced:
            ai_result = forced
        else:
            unrealized_pct = 0.0
            if current_pos and float(current_pos.get("avg_cost", 0.0)) > 0:
                base = float(current_pos["avg_cost"])
                px = float(indicators["price"])
                if str(current_pos.get("side", "")).upper() == "LONG":
                    unrealized_pct = ((px - base) / base) * 100.0
                else:
                    unrealized_pct = ((base - px) / base) * 100.0
            ai_result = get_trading_decision(
                indicators,
                cfg,
                position_context={
                    "side": current_pos.get("side") if current_pos else None,
                    "quantity": round(float(current_pos.get("quantity", 0.0)), 6) if current_pos else 0.0,
                    "avg_cost": round(float(current_pos.get("avg_cost", 0.0)), 4) if current_pos else 0.0,
                    "unrealized_pct": round(unrealized_pct, 2),
                },
            )
    except EnvironmentError as exc:
        reason = str(exc)
        _log_rule_event(target_asset, "ai_error", "SKIP", reason, source=source)
        return {
            "asset": target_asset,
            "decision": "SKIP",
            "skipped": True,
            "skip_reason": reason,
            "indicators": indicators,
            "run_source": source,
        }
    except Exception as exc:
        reason = f"AI error: {exc}"
        _log_rule_event(target_asset, "ai_error", "SKIP", reason, source=source)
        return {
            "asset": target_asset,
            "decision": "SKIP",
            "skipped": True,
            "skip_reason": reason,
            "indicators": indicators,
            "run_source": source,
        }

    wallet = database.get_wallet()
    open_positions = _count_open_positions(engine)
    ai_result, block_reason = _enforce_rule_engine(
        cfg=cfg,
        indicators=indicators,
        current_pos=current_pos,
        ai_result=ai_result,
        wallet_balance=float(wallet.get("balance", 0.0)),
        open_positions=open_positions,
    )
    if block_reason:
        _log_rule_event(
            target_asset,
            "rule_block",
            "SKIP",
            block_reason,
            source=source,
            confidence=int(ai_result.get("confidence", 0)),
        )
        return {
            "asset": target_asset,
            "decision": "SKIP",
            "skipped": True,
            "skip_reason": block_reason,
            "indicators": indicators,
            "confidence": ai_result.get("confidence", 0),
            "reason": ai_result.get("reason", ""),
            "run_source": source,
        }

    result = engine.execute(
        asset=target_asset,
        decision=ai_result["decision"],
        price=indicators["price"],
        confidence=ai_result["confidence"],
        reason=ai_result["reason"],
        trade_amount=float(ai_result.get("_trade_notional", cfg.get("trade_amount", 10_000))),
        style=cfg.get("style", "short_term"),
        slippage_bps=float(cfg.get("execution_slippage_bps", 5.0)),
        fee_bps=float(cfg.get("brokerage_fee_bps", 2.0)),
        fixed_fee_per_order=float(cfg.get("fixed_fee_per_order", 0.0)),
    )

    if result.get("skipped"):
        _log_rule_event(
            target_asset,
            "engine_skip",
            result.get("decision"),
            result.get("skip_reason", ""),
            source=source,
            confidence=int(result.get("confidence", 0) or 0),
        )
    else:
        _log_rule_event(
            target_asset,
            "trade_executed",
            result.get("decision"),
            result.get("reason", ""),
            source=source,
            confidence=int(result.get("confidence", 0) or 0),
        )

    universe_key = _resolve_universe_key(cfg)
    return {
        **result,
        "indicators": indicators,
        "run_source": source,
        "settings_used": {
            "market": "indian_stocks",
            "stock_universe": universe_key,
            "stock_universe_label": UNIVERSE_LABELS[universe_key],
            "style": cfg.get("style"),
            "risk": cfg.get("risk"),
            "trade_amount": cfg.get("trade_amount"),
            "loop_interval_seconds": _get_loop_interval_seconds(cfg),
            "execution_slippage_bps": cfg.get("execution_slippage_bps"),
            "brokerage_fee_bps": cfg.get("brokerage_fee_bps"),
            "fixed_fee_per_order": cfg.get("fixed_fee_per_order"),
            "indicator_period": period,
            "indicator_interval": interval,
            "rsi_min": cfg.get("rsi_min"),
            "rsi_max": cfg.get("rsi_max"),
            "min_price": cfg.get("min_price"),
            "max_price": cfg.get("max_price"),
            "min_volume": cfg.get("min_volume"),
            "require_uptrend": cfg.get("require_uptrend"),
        },
    }


def _run_universe_cycle(cfg: dict, source: str = "auto") -> dict:
    assets = _select_cycle_assets(cfg)
    if not assets:
        raise HTTPException(
            status_code=400,
            detail="No stocks to scan: empty watchlist or universe. Add symbols to assets or turn off watchlist-only.",
        )

    allowed, session_reason = _session_allows_trading(cfg)
    if not allowed:
        universe_key = _resolve_universe_key(cfg)
        logger.info("Trading cycle skipped (session): %s", session_reason)
        return {
            "run_source": source,
            "stock_universe": universe_key,
            "stock_universe_label": UNIVERSE_LABELS[universe_key],
            "total_assets": len(assets),
            "executed_trades": 0,
            "skipped_assets": 0,
            "session_blocked": True,
            "session_reason": session_reason,
            "results": [],
        }

    # Invalidate stats cache at the start of each fresh cycle so all assets
    # share one DB read instead of one per asset.
    _daily_trade_stats(force_refresh=True)

    results: list[dict] = []
    executed = 0
    skipped = 0

    # Parallelise market-data fetches across up to 8 threads.
    max_workers = min(8, len(assets))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_one_asset, cfg, asset, source): asset for asset in assets}
        for future in as_completed(futures):
            try:
                out = future.result()
            except Exception as exc:
                asset_name = futures[future]
                logger.exception("Unexpected error running asset %s: %s", asset_name, exc)
                out = {
                    "asset": asset_name,
                    "decision": "SKIP",
                    "skipped": True,
                    "skip_reason": f"Unexpected error: {exc}",
                    "run_source": source,
                }
            results.append(out)
            if out.get("skipped"):
                skipped += 1
            elif out.get("decision") in {"BUY", "SELL"}:
                executed += 1

    universe_key = _resolve_universe_key(cfg)
    logger.info(
        "Cycle complete [%s]: %d executed, %d skipped / %d total",
        universe_key, executed, skipped, len(assets),
    )
    return {
        "run_source": source,
        "stock_universe": universe_key,
        "stock_universe_label": UNIVERSE_LABELS[universe_key],
        "total_assets": len(assets),
        "executed_trades": executed,
        "skipped_assets": skipped,
        "results": results,
    }


def _auto_loop_worker():
    global _loop_running, _loop_last_error, _loop_last_run_at
    while not _loop_stop.is_set():
        cfg = settings_module.load_settings()
        if not cfg.get("auto_start", False):
            break

        interval_seconds = _get_loop_interval_seconds(cfg)

        try:
            summary = _run_universe_cycle(cfg, source="auto")
            _loop_last_error = ""
            if summary.get("session_blocked"):
                _loop_last_error = summary.get("session_reason") or "NSE session closed."
            elif summary.get("executed_trades", 0) == 0:
                _loop_last_error = "No executable trades in last cycle (filters or HOLD decisions)."
            _loop_last_run_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        except Exception as exc:
            _loop_last_error = str(exc)

        if _loop_stop.wait(interval_seconds):
            break

    _loop_running = False


def _start_auto_loop_if_needed(force: bool = False) -> bool:
    global _loop_thread, _loop_running
    with _loop_lock:
        cfg = settings_module.load_settings()
        should_start = force or cfg.get("auto_start", False)
        if not should_start or _loop_running:
            return False

        _loop_stop.clear()
        _loop_running = True
        _loop_thread = Thread(target=_auto_loop_worker, daemon=True)
        _loop_thread.start()
        return True


def _stop_auto_loop() -> bool:
    global _loop_running
    with _loop_lock:
        was_running = _loop_running
        _loop_stop.set()
        _loop_running = False
        return was_running


def _compute_portfolio_snapshot() -> dict:
    engine = get_engine()
    wallet = database.get_wallet()
    cash_balance = float(wallet["balance"])

    raw_positions = engine.get_position_details()
    symbols = [asset for asset, pos in raw_positions.items() if abs(float(pos.get("quantity", 0.0))) > 0]
    live_quotes = {}
    try:
        live_quotes = fetch_live_quotes(symbols, use_fallback=True)
    except Exception:
        live_quotes = {}
    fallback_close = fetch_bulk_last_close(symbols, period="7d", interval="1d")

    positions = []
    total_market_value = 0.0
    total_unrealized = 0.0

    for asset, pos in raw_positions.items():
        qty = float(pos["quantity"])
        avg_cost = float(pos["avg_cost"])
        if qty == 0:
            continue

        last_price = live_quotes.get(asset, {}).get("price")
        price_source = "live"
        market_value = 0.0
        unrealized = 0.0
        if last_price is not None:
            try:
                last_price = float(last_price)
            except Exception:
                last_price = None
        if last_price is None:
            last_price = fallback_close.get(asset)
            price_source = "eod_fallback" if last_price is not None else "cost_fallback"
        if last_price is None:
            # Prevent false portfolio loss when quote provider misses a symbol.
            # Mark the position at cost until live quote is available.
            last_price = avg_cost
            price_source = "cost_fallback"
        if last_price is not None:
            market_value = qty * last_price
            unrealized = (last_price - avg_cost) * qty

        total_market_value += market_value
        total_unrealized += unrealized

        positions.append(
            {
                "asset": asset,
                "quantity": round(qty, 6),
                "avg_cost": round(avg_cost, 4),
                "last_price": round(last_price, 4) if last_price is not None else None,
                "price_source": price_source,
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized, 2),
            }
        )

    total_equity = cash_balance + total_market_value
    total_pnl = total_equity - STARTING_BALANCE

    return {
        "cash_balance": round(cash_balance, 2),
        "balance": round(total_equity, 2),
        "total_equity": round(total_equity, 2),
        "starting_balance": STARTING_BALANCE,
        "total_market_value": round(total_market_value, 2),
        "unrealized_pnl": round(total_unrealized, 2),
        "total_pnl": round(total_pnl, 2),
        "trade_count": wallet["trade_count"],
        "holdings": {p["asset"]: p["quantity"] for p in positions if p["quantity"] > 0},
        "positions": positions,
    }


def _performance_report(limit: int = 1000) -> dict:
    fetch_limit = max(10, min(5000, int(limit)))
    trades = _annotate_trades(database.get_trades(limit=fetch_limit))
    closed = [t for t in trades if t.get("is_closing_trade")]
    wins = [t for t in closed if float(t.get("profit") or 0.0) > 0]
    losses = [t for t in closed if float(t.get("profit") or 0.0) < 0]

    realized_total = sum(float(t.get("profit") or 0.0) for t in trades)
    gross_profit = sum(float(t.get("profit") or 0.0) for t in wins)
    gross_loss = sum(float(t.get("profit") or 0.0) for t in losses)
    closed_count = len(closed)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / closed_count) if closed_count else 0.0
    avg_win = (gross_profit / win_count) if win_count else 0.0
    avg_loss = (gross_loss / loss_count) if loss_count else 0.0
    profit_factor = (
        gross_profit / abs(gross_loss)
        if gross_loss < 0
        else (float("inf") if gross_profit > 0 else 0.0)
    )
    expectancy = (win_rate * avg_win) + ((1.0 - win_rate) * avg_loss)
    today = _utc_now().date()
    date_keys = [(today - timedelta(days=days)).isoformat() for days in range(6, -1, -1)]
    daily_realized: dict[str, float] = {d: 0.0 for d in date_keys}
    for trade in trades:
        ts = _parse_trade_time(str(trade.get("timestamp", "")))
        if not ts:
            continue
        d = ts.date().isoformat()
        if d in daily_realized:
            daily_realized[d] += float(trade.get("profit") or 0.0)
    daily_series = [
        {"date": d, "label": d[5:], "realized_pnl": round(daily_realized[d], 2)}
        for d in date_keys
    ]

    snapshot = _compute_portfolio_snapshot()
    return {
        "window_trades": len(trades),
        "window_closed_trades": closed_count,
        "wins": win_count,
        "losses": loss_count,
        "win_rate": round(win_rate, 4),
        "realized_pnl_window": round(realized_total, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": (round(profit_factor, 4) if profit_factor != float("inf") else "inf"),
        "expectancy_per_trade": round(expectancy, 2),
        "daily_realized_last_7d": daily_series,
        "portfolio_total_pnl": snapshot.get("total_pnl", 0.0),
        "portfolio_unrealized_pnl": snapshot.get("unrealized_pnl", 0.0),
        "portfolio_total_equity": snapshot.get("total_equity", 0.0),
    }


def _annotate_trades(trades: list[dict]) -> list[dict]:
    """Add derived action metadata so the UI can distinguish opening vs closing trades."""
    holdings: dict[str, float] = {}
    avg_entry_price: dict[str, float] = {}
    annotated_oldest_first: list[dict] = []

    for trade in reversed(trades):
        asset = str(trade.get("asset", "")).upper()
        decision = str(trade.get("decision", "")).upper()
        quantity = float(trade.get("quantity") or 0.0)
        price = float(trade.get("price") or 0.0)
        held_before = float(holdings.get(asset, 0.0))
        avg_before = float(avg_entry_price.get(asset, 0.0))

        action_type = "hold"
        is_closing_trade = False
        entry_price = None
        exit_price = None

        if decision == "BUY":
            if held_before < 0:
                action_type = "close_short"
                is_closing_trade = True
                entry_price = avg_before if avg_before > 0 else None
                exit_price = price if price > 0 else None
                holdings[asset] = 0.0
                avg_entry_price[asset] = 0.0
            elif held_before > 0:
                action_type = "add_long"
                new_qty = held_before + quantity
                holdings[asset] = new_qty
                avg_entry_price[asset] = (((held_before * avg_before) + (quantity * price)) / new_qty) if new_qty > 0 else 0.0
            else:
                action_type = "open_long"
                holdings[asset] = quantity
                avg_entry_price[asset] = price if quantity > 0 else 0.0
        elif decision == "SELL":
            if held_before > 0:
                action_type = "close_long"
                is_closing_trade = True
                entry_price = avg_before if avg_before > 0 else None
                exit_price = price if price > 0 else None
                holdings[asset] = 0.0
                avg_entry_price[asset] = 0.0
            elif held_before < 0:
                action_type = "add_short"
                new_abs_qty = abs(held_before) + quantity
                holdings[asset] = held_before - quantity
                avg_entry_price[asset] = (((abs(held_before) * avg_before) + (quantity * price)) / new_abs_qty) if new_abs_qty > 0 else 0.0
            else:
                action_type = "open_short"
                holdings[asset] = -quantity
                avg_entry_price[asset] = price if quantity > 0 else 0.0

        annotated_oldest_first.append(
            {
                **trade,
                "action_type": action_type,
                "is_closing_trade": is_closing_trade,
                "entry_price": round(entry_price, 4) if entry_price is not None else None,
                "exit_price": round(exit_price, 4) if exit_price is not None else None,
            }
        )

    return list(reversed(annotated_oldest_first))


# ---------------------------------------------------------------------------
# Lifecycle hooks are handled by the `lifespan` context manager above.


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "message": "GenAI Paper Trading Agent is running"}


@app.get("/healthz", tags=["Health"])
def healthz():
    """
    Liveness probe: confirms API process is responsive.
    """
    return {"status": "ok"}


@app.get("/readyz", tags=["Health"])
def readyz():
    """
    Readiness probe: confirms critical dependencies are available.
    """
    checks = {
        "openai_api_key_configured": bool(OPENAI_API_KEY),
        "database_available": True,
    }
    try:
        _ = database.get_wallet()
    except Exception:
        checks["database_available"] = False

    ready = all(checks.values())
    status_code = 200 if ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if ready else "not_ready",
            "checks": checks,
        },
    )


@app.get("/universes", tags=["Settings"])
def universes():
    return {
        "universes": [
            {
                "key": key,
                "label": UNIVERSE_LABELS[key],
                "count": len(UNIVERSE_ASSETS[key]),
            }
            for key in CANONICAL_UNIVERSES
        ]
    }


@app.post("/run", tags=["Trading"], dependencies=[Depends(_require_api_token)])
def run_agent(
    asset: str = Query(default=None, description="Ticker to trade. Leave empty to scan full universe."),
):
    cfg = settings_module.load_settings()
    if asset:
        return _run_one_asset(cfg, asset, source="manual")
    return _run_universe_cycle(cfg, source="manual")


@app.get("/quotes", tags=["Market"])
def get_quotes(assets: Optional[str] = Query(default=None, description="Comma-separated tickers")):
    cfg = settings_module.load_settings()
    allowed = set(_resolve_assets(cfg))
    if assets:
        requested = [a.strip().upper() for a in assets.split(",") if a.strip()]
        tickers = [a for a in requested if a in allowed]
    else:
        tickers = list(allowed)

    quotes = fetch_live_quotes(tickers, use_fallback=True)
    return {
        "count": len(quotes),
        "quotes": quotes,
        "requested": tickers,
    }


@app.post("/market/live-data", tags=["Market"], dependencies=[Depends(_require_api_token)])
def get_live_market_data(body: LiveDataRequest):
    """
    Fetch live snapshot + 5d/1m historical data for Indian symbols.
    """
    exchange = str(body.exchange).upper().strip()
    if exchange not in {"NSE", "BSE"}:
        raise HTTPException(status_code=400, detail="exchange must be NSE or BSE")
    if not body.symbols:
        raise HTTPException(status_code=400, detail="symbols cannot be empty")

    try:
        summary_df, history_map, _combined = fetch_live_market_data(
            symbols=body.symbols,
            exchange=exchange,
            retries=max(1, min(5, int(body.retries))),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"live data fetch failed: {exc}")

    payload = {
        "exchange": exchange,
        "count": int(len(summary_df)),
        "summary": summary_df.to_dict(orient="records"),
    }

    if body.include_history:
        history_payload: dict[str, list[dict]] = {}
        for sym, hist in history_map.items():
            safe = hist.reset_index().copy()
            if not safe.empty:
                first_col = safe.columns[0]
                safe[first_col] = safe[first_col].astype(str)
            history_payload[sym] = safe.to_dict(orient="records")
        payload["history_5d_1m"] = history_payload

    return payload


@app.get("/portfolio", tags=["Portfolio"])
def portfolio():
    return _compute_portfolio_snapshot()


@app.get("/history", tags=["Portfolio"])
def history(
    limit: int = Query(default=50, ge=1, le=500),
    closed_only: bool = Query(default=False, description="Return only closing trades"),
):
    fetch_limit = 5000 if closed_only else limit
    trades = _annotate_trades(database.get_trades(limit=fetch_limit))
    if closed_only:
        trades = [t for t in trades if t.get("is_closing_trade")][:limit]
    return {"count": len(trades), "trades": trades}


@app.get("/rule-logs", tags=["Portfolio"])
def rule_logs(limit: int = Query(default=100, ge=1, le=1000)):
    logs = database.get_rule_logs(limit=limit)
    return {"count": len(logs), "logs": logs}


@app.get("/performance/report", tags=["Portfolio"])
def performance_report(limit: int = Query(default=1000, ge=10, le=5000)):
    return _performance_report(limit=limit)


@app.get("/settings", tags=["Settings"])
def get_settings():
    cfg = settings_module.load_settings()
    universe = _resolve_universe_key(cfg)
    universe_assets = _resolve_assets(cfg)
    watchlist_assets = [str(a).upper().strip() for a in (cfg.get("assets") or []) if str(a).strip()]
    cfg["market"] = "indian_stocks"
    cfg["stock_universe"] = universe
    cfg["assets"] = watchlist_assets
    cfg["universe_assets"] = universe_assets
    cfg["universe_asset_count"] = len(universe_assets)
    cfg["cycle_asset_count"] = len(_select_cycle_assets(cfg))
    return cfg


@app.patch("/settings", tags=["Settings"], dependencies=[Depends(_require_api_token)])
def update_settings(body: SettingsUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields provided.")

    if "stock_universe" in updates:
        key = UNIVERSE_ALIASES.get(str(updates["stock_universe"]).strip().lower(), str(updates["stock_universe"]).strip().lower())
        if key not in UNIVERSE_ASSETS:
            raise HTTPException(status_code=400, detail="Invalid stock_universe value.")
        updates["stock_universe"] = key

    if "loop_interval_seconds" in updates:
        try:
            val = int(updates["loop_interval_seconds"])
        except Exception as exc:
            raise HTTPException(status_code=400, detail="loop_interval_seconds must be an integer.") from exc
        if val < 5 or val > 300:
            raise HTTPException(status_code=400, detail="loop_interval_seconds must be between 5 and 300.")
        updates["loop_interval_seconds"] = val
    if "respect_market_hours" in updates:
        updates["respect_market_hours"] = bool(updates["respect_market_hours"])
    if "watchlist_only" in updates:
        updates["watchlist_only"] = bool(updates["watchlist_only"])
    if "require_fresh_indicators" in updates:
        updates["require_fresh_indicators"] = bool(updates["require_fresh_indicators"])
    if "max_symbols_per_cycle" in updates:
        try:
            msc = int(updates["max_symbols_per_cycle"])
        except Exception as exc:
            raise HTTPException(status_code=400, detail="max_symbols_per_cycle must be an integer.") from exc
        if msc < 0 or msc > 200:
            raise HTTPException(status_code=400, detail="max_symbols_per_cycle must be between 0 and 200 (0 = no cap).")
        updates["max_symbols_per_cycle"] = msc
    if "execution_slippage_bps" in updates:
        updates["execution_slippage_bps"] = float(updates["execution_slippage_bps"])
    if "brokerage_fee_bps" in updates:
        updates["brokerage_fee_bps"] = float(updates["brokerage_fee_bps"])
    if "fixed_fee_per_order" in updates:
        updates["fixed_fee_per_order"] = float(updates["fixed_fee_per_order"])

    # Validate filters.
    if "rsi_min" in updates:
        updates["rsi_min"] = float(updates["rsi_min"])
    if "rsi_max" in updates:
        updates["rsi_max"] = float(updates["rsi_max"])
    if "min_price" in updates:
        updates["min_price"] = float(updates["min_price"])
    if "max_price" in updates:
        updates["max_price"] = float(updates["max_price"])
    if "min_volume" in updates:
        updates["min_volume"] = float(updates["min_volume"])
    if "risk_per_trade_pct" in updates:
        updates["risk_per_trade_pct"] = float(updates["risk_per_trade_pct"])
    if "max_daily_loss_pct" in updates:
        updates["max_daily_loss_pct"] = float(updates["max_daily_loss_pct"])
    if "stop_loss_pct" in updates:
        updates["stop_loss_pct"] = float(updates["stop_loss_pct"])
    if "take_profit_pct" in updates:
        updates["take_profit_pct"] = float(updates["take_profit_pct"])
    if "min_rr" in updates:
        updates["min_rr"] = float(updates["min_rr"])
    if "min_confidence" in updates:
        updates["min_confidence"] = int(updates["min_confidence"])
    if "max_open_positions" in updates:
        updates["max_open_positions"] = int(updates["max_open_positions"])
    if "max_trades_per_day" in updates:
        updates["max_trades_per_day"] = int(updates["max_trades_per_day"])
    if "loss_streak_cooldown" in updates:
        updates["loss_streak_cooldown"] = int(updates["loss_streak_cooldown"])
    if "cooldown_minutes" in updates:
        updates["cooldown_minutes"] = int(updates["cooldown_minutes"])
    if "max_holding_minutes_day_trade" in updates:
        updates["max_holding_minutes_day_trade"] = int(updates["max_holding_minutes_day_trade"])

    # Keep market pinned to Indian stocks.
    updates["market"] = "indian_stocks"

    current = settings_module.load_settings()
    candidate = {**current, **updates}

    if float(candidate.get("rsi_min", 0)) > float(candidate.get("rsi_max", 100)):
        raise HTTPException(status_code=400, detail="rsi_min must be <= rsi_max")
    if float(candidate.get("min_price", 0)) > float(candidate.get("max_price", 1_000_000)):
        raise HTTPException(status_code=400, detail="min_price must be <= max_price")
    if int(candidate.get("min_confidence", 60)) < 0 or int(candidate.get("min_confidence", 60)) > 100:
        raise HTTPException(status_code=400, detail="min_confidence must be between 0 and 100")
    if float(candidate.get("risk_per_trade_pct", 0.01)) <= 0 or float(candidate.get("risk_per_trade_pct", 0.01)) > 0.2:
        raise HTTPException(status_code=400, detail="risk_per_trade_pct must be in (0, 0.2]")
    if float(candidate.get("max_daily_loss_pct", 0.03)) <= 0 or float(candidate.get("max_daily_loss_pct", 0.03)) > 0.5:
        raise HTTPException(status_code=400, detail="max_daily_loss_pct must be in (0, 0.5]")
    if float(candidate.get("stop_loss_pct", 0.015)) <= 0:
        raise HTTPException(status_code=400, detail="stop_loss_pct must be > 0")
    if float(candidate.get("take_profit_pct", 0.03)) <= 0:
        raise HTTPException(status_code=400, detail="take_profit_pct must be > 0")
    if float(candidate.get("execution_slippage_bps", 5.0)) < 0 or float(candidate.get("execution_slippage_bps", 5.0)) > 100:
        raise HTTPException(status_code=400, detail="execution_slippage_bps must be between 0 and 100")
    if float(candidate.get("brokerage_fee_bps", 2.0)) < 0 or float(candidate.get("brokerage_fee_bps", 2.0)) > 100:
        raise HTTPException(status_code=400, detail="brokerage_fee_bps must be between 0 and 100")
    if float(candidate.get("fixed_fee_per_order", 0.0)) < 0 or float(candidate.get("fixed_fee_per_order", 0.0)) > 1000:
        raise HTTPException(status_code=400, detail="fixed_fee_per_order must be between 0 and 1000")

    saved = settings_module.save_settings(updates)

    if "auto_start" in updates:
        if updates["auto_start"]:
            _start_auto_loop_if_needed(force=True)
        else:
            _stop_auto_loop()

    universe = _resolve_universe_key(saved)
    saved["assets"] = [str(a).upper().strip() for a in (saved.get("assets") or []) if str(a).strip()]
    saved["universe_assets"] = _resolve_assets(saved)
    saved["stock_universe"] = universe
    saved["market"] = "indian_stocks"
    saved["universe_asset_count"] = len(saved["universe_assets"])
    saved["cycle_asset_count"] = len(_select_cycle_assets(saved))

    return {"message": "Settings updated.", "settings": saved}


@app.post("/autotrade/start", tags=["Trading"], dependencies=[Depends(_require_api_token)])
def start_auto_trading():
    settings_module.save_settings({"auto_start": True})
    started = _start_auto_loop_if_needed(force=True)
    return {"running": _loop_running, "started": started}


@app.post("/autotrade/stop", tags=["Trading"], dependencies=[Depends(_require_api_token)])
def stop_auto_trading():
    settings_module.save_settings({"auto_start": False})
    stopped = _stop_auto_loop()
    return {"running": _loop_running, "stopped": stopped}


@app.get("/autotrade/status", tags=["Trading"])
def auto_trading_status():
    cfg = settings_module.load_settings()
    universe = _resolve_universe_key(cfg)
    universe_assets = _resolve_assets(cfg)
    watchlist_assets = [str(a).upper().strip() for a in (cfg.get("assets") or []) if str(a).strip()]
    open_now, session_detail = nse_regular_session_status()
    respect = bool(cfg.get("respect_market_hours", True))
    cycle_syms = _select_cycle_assets(cfg)
    return {
        "running": _loop_running,
        "auto_start": bool(cfg.get("auto_start", False)),
        "interval_seconds": _get_loop_interval_seconds(cfg),
        "last_run_at": _loop_last_run_at,
        "last_error": _loop_last_error,
        "stock_universe": universe,
        "stock_universe_label": UNIVERSE_LABELS[universe],
        "assets": universe_assets,
        "respect_market_hours": respect,
        "nse_session_open": open_now if respect else True,
        "nse_session_detail": session_detail if respect else "respect_market_hours is off",
        "watchlist_only": bool(cfg.get("watchlist_only", False)),
        "watchlist_assets": watchlist_assets,
        "max_symbols_per_cycle": int(cfg.get("max_symbols_per_cycle") or 0),
        "require_fresh_indicators": bool(cfg.get("require_fresh_indicators", True)),
        "universe_asset_count": len(universe_assets),
        "cycle_asset_count": len(cycle_syms),
        "cycle_assets_preview": cycle_syms[:12],
    }


@app.post("/reset", tags=["Admin"], dependencies=[Depends(_require_api_token)])
def reset(confirm: bool = Query(default=False, description="Must be true to execute reset.")):
    """
    Reset wallet and all trade history. Requires ?confirm=true to prevent accidental resets.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Safety check: add ?confirm=true to the request to confirm the reset.",
        )
    database.reset_wallet()
    engine = get_engine()
    engine.reset_positions()
    logger.warning("Wallet and all trade history have been RESET.")
    return {"message": "Wallet and trade history reset.", "balance": STARTING_BALANCE}
