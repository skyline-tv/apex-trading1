from __future__ import annotations

import time
from typing import Dict, List, Tuple

import pandas as pd
import yfinance as yf


def normalize_symbol(symbol: str, exchange: str = "NSE") -> str:
    """
    Append Indian exchange suffix if missing:
      NSE -> .NS
      BSE -> .BO
    """
    sym = str(symbol).strip().upper()
    if sym.endswith(".NS") or sym.endswith(".BO"):
        return sym
    suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
    return f"{sym}{suffix}"


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


def _fetch_one_symbol(symbol: str, exchange: str = "NSE", retries: int = 3) -> Tuple[dict, pd.DataFrame]:
    full_symbol = normalize_symbol(symbol, exchange)
    ticker = yf.Ticker(full_symbol)

    for attempt in range(1, retries + 1):
        try:
            intraday = ticker.history(period="1d", interval="1m", auto_adjust=False)
            if intraday.empty:
                raise ValueError("No intraday data returned.")

            ltp = float(intraday["Close"].dropna().iloc[-1])
            day_high = float(intraday["High"].max())
            day_low = float(intraday["Low"].min())
            volume = float(intraday["Volume"].fillna(0).sum())

            hist_5d_1m = ticker.history(period="5d", interval="1m", auto_adjust=False)
            if hist_5d_1m.empty:
                raise ValueError("No 5-day, 1-minute historical data returned.")

            return {
                "symbol": full_symbol,
                "ltp": round(ltp, 2),
                "day_high": round(day_high, 2),
                "day_low": round(day_low, 2),
                "volume": int(volume),
                "rows_5d_1m": len(hist_5d_1m),
            }, hist_5d_1m

        except Exception as exc:
            if attempt < retries and _is_rate_limit_error(exc):
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"{full_symbol}: {exc}") from exc

    raise RuntimeError(f"{full_symbol}: failed after retries")


def fetch_live_market_data(
    symbols: List[str],
    exchange: str = "NSE",
    retries: int = 3,
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], pd.DataFrame]:
    """
    Returns:
      1) summary_df: LTP/day high/day low/volume table
      2) history_map: per-symbol 5d/1m DataFrame
      3) combined_history_df: all symbols combined with symbol column
    """
    if not symbols:
        raise ValueError("symbols list cannot be empty")

    summary_rows: list[dict] = []
    history_map: Dict[str, pd.DataFrame] = {}

    for sym in symbols:
        try:
            row, hist = _fetch_one_symbol(sym, exchange=exchange, retries=retries)
            summary_rows.append(row)
            history_map[row["symbol"]] = hist
        except Exception as exc:
            summary_rows.append(
                {
                    "symbol": normalize_symbol(sym, exchange),
                    "ltp": None,
                    "day_high": None,
                    "day_low": None,
                    "volume": None,
                    "rows_5d_1m": 0,
                    "error": str(exc),
                }
            )

    summary_df = pd.DataFrame(summary_rows).sort_values("symbol").reset_index(drop=True)

    frames: list[pd.DataFrame] = []
    for sym, hist in history_map.items():
        temp = hist.copy().reset_index()
        temp["symbol"] = sym
        frames.append(temp)
    combined_history_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    return summary_df, history_map, combined_history_df

