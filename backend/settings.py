import json
import os
from pathlib import Path
from threading import Lock

SETTINGS_FILE = Path(__file__).parent / "settings.json"

DEFAULT_SETTINGS = {
    "market": "indian_stocks",
    "stock_universe": "nifty_50",
    "style": "short_term",
    "risk": "medium",
    "trade_amount": 10000,
    "risk_per_trade_pct": 0.01,
    "min_confidence": 60,
    "max_daily_loss_pct": 0.03,
    "max_open_positions": 8,
    "max_trades_per_day": 30,
    "loss_streak_cooldown": 3,
    "cooldown_minutes": 30,
    "stop_loss_pct": 0.015,
    "take_profit_pct": 0.03,
    "min_rr": 1.5,
    "max_holding_minutes_day_trade": 180,
    "no_averaging_down": True,
    "rsi_min": 0,
    "rsi_max": 100,
    "min_price": 0,
    "max_price": 1000000,
    "min_volume": 0,
    "require_uptrend": False,
    "auto_start": False,
    "respect_market_hours": True,
    "watchlist_only": False,
    "max_symbols_per_cycle": 20,
    "require_fresh_indicators": True,
    "loop_interval_seconds": 20,
    "execution_slippage_bps": 5.0,
    "brokerage_fee_bps": 2.0,
    "fixed_fee_per_order": 0.0,
    "assets": ["RELIANCE.NS", "TCS.NS"],
}

# Thread-safe lock: auto-trading loop reads settings concurrently with PATCH requests.
_settings_lock = Lock()


def load_settings() -> dict:
    """Load settings from settings.json, falling back to defaults."""
    with _settings_lock:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
            # Merge with defaults so missing keys are filled in
            return {**DEFAULT_SETTINGS, **data}
        return DEFAULT_SETTINGS.copy()


def save_settings(new_settings: dict) -> dict:
    """Merge and persist updated settings."""
    with _settings_lock:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r") as f:
                current = json.load(f)
            current = {**DEFAULT_SETTINGS, **current}
        else:
            current = DEFAULT_SETTINGS.copy()
        current.update(new_settings)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(current, f, indent=2)
        return current
