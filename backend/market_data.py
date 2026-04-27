import logging
import time
from threading import Lock
from urllib.parse import quote

import pandas as pd
import requests
import ta
import yfinance as yf

from symbol_utils import normalize_ticker, normalize_tickers

# yfinance can emit noisy "possibly delisted" messages for temporary upstream
# failures/rate limits; keep backend logs readable.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("yfinance.shared").setLevel(logging.CRITICAL)

_FAILED_SYMBOLS: dict[str, float] = {}
_FAIL_COOLDOWN_SEC = 120
_YFINANCE_DOWNLOAD_LOCK = Lock()
logger = logging.getLogger(__name__)


def _last_bar_as_of_iso(df: pd.DataFrame) -> str | None:
    """UTC ISO timestamp of the last OHLCV row (for freshness checks)."""
    if df is None or df.empty or len(df.index) == 0:
        return None
    idx = df.index[-1]
    if not isinstance(idx, pd.Timestamp):
        return None
    ts = idx
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.isoformat()


def fetch_indicators(ticker: str, period: str = "3mo", interval: str = "1d") -> dict:
    """
    Download OHLCV data for `ticker` and compute RSI, MA20, MA50.
    Returns a flat dict with the latest values, or raises on failure.
    """
    symbol = normalize_ticker(ticker)
    last_error: Exception | None = None
    df: pd.DataFrame | None = None
    for attempt in range(4):
        try:
            with _YFINANCE_DOWNLOAD_LOCK:
                df = yf.download(
                    symbol,
                    period=period,
                    interval=interval,
                    progress=False,
                    auto_adjust=True,
                    threads=False,
                )
            if df is not None and not df.empty:
                break
        except Exception as exc:
            last_error = exc
            logger.warning("yfinance download failed %s (attempt %s): %s", symbol, attempt + 1, exc)
        time.sleep(min(8.0, 1.0 * (2**attempt)))
    if df is None or df.empty:
        msg = f"No data returned for ticker: {symbol}"
        if last_error:
            msg += f" ({last_error})"
        raise ValueError(msg)

    # Flatten MultiIndex columns if present (yfinance >= 0.2 may return them)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close: pd.Series = df["Close"].dropna()
    volume: pd.Series = df["Volume"].dropna() if "Volume" in df.columns else pd.Series(dtype=float)

    if len(close) < 51:
        raise ValueError(
            f"Not enough data to compute indicators for {symbol} "
            f"(got {len(close)} bars, need >= 51)"
        )

    rsi_series = ta.momentum.RSIIndicator(close=close, window=14).rsi()
    ma20_series = ta.trend.SMAIndicator(close=close, window=20).sma_indicator()
    ma50_series = ta.trend.SMAIndicator(close=close, window=50).sma_indicator()
    macd_indicator = ta.trend.MACD(close=close)
    bb_indicator = ta.volatility.BollingerBands(close=close, window=20)

    as_of = _last_bar_as_of_iso(df)

    return {
        "ticker": symbol,
        "as_of": as_of,
        "bar_period": period,
        "bar_interval": interval,
        "price": round(float(close.iloc[-1]), 4),
        "rsi": round(float(rsi_series.iloc[-1]), 2),
        "ma20": round(float(ma20_series.iloc[-1]), 4),
        "ma50": round(float(ma50_series.iloc[-1]), 4),
        "macd": round(float(macd_indicator.macd().iloc[-1]), 4),
        "macd_signal": round(float(macd_indicator.macd_signal().iloc[-1]), 4),
        "macd_diff": round(float(macd_indicator.macd_diff().iloc[-1]), 4),
        "bb_upper": round(float(bb_indicator.bollinger_hband().iloc[-1]), 4),
        "bb_lower": round(float(bb_indicator.bollinger_lband().iloc[-1]), 4),
        "bb_mid": round(float(bb_indicator.bollinger_mavg().iloc[-1]), 4),
        "volume": round(float(volume.iloc[-1]), 2) if not volume.empty else 0.0,
        "avg_volume_20": round(float(volume.tail(20).mean()), 2) if not volume.empty else 0.0,
    }


def fetch_live_quotes(tickers: list[str], use_fallback: bool = True) -> dict[str, dict]:
    """
    Fetch near real-time quotes from Yahoo's quote endpoint for multiple symbols.
    Returns:
      {
        "RELIANCE.NS": {"price": 2812.4, "change": 12.2, "change_percent": 0.44},
        ...
      }
    """
    cleaned = normalize_tickers(tickers)
    if not cleaned:
        return {}

    result: dict[str, dict] = {}

    def _get_json(url: str) -> dict:
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_exc = exc
                time.sleep(min(8.0, 1.0 * (2**attempt)))
        raise RuntimeError(f"Yahoo quote request failed after retries: {last_exc}") from last_exc

    # Fetch in chunks to reduce failures/rate-limit spikes for large universes.
    chunk_size = 25
    for i in range(0, len(cleaned), chunk_size):
        chunk = cleaned[i : i + chunk_size]
        try:
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={quote(','.join(chunk))}"
            payload = _get_json(url)
            for item in payload.get("quoteResponse", {}).get("result", []):
                symbol = normalize_ticker(item.get("symbol", ""))
                if not symbol:
                    continue
                price = item.get("regularMarketPrice")
                if price is None:
                    continue
                result[symbol] = {
                    "price": float(price),
                    "change": float(item.get("regularMarketChange") or 0.0),
                    "change_percent": float(item.get("regularMarketChangePercent") or 0.0),
                    "timestamp": item.get("regularMarketTime"),
                    "currency": item.get("currency"),
                    "source": "yahoo_quote",
                }
        except Exception:
            # Rate-limits can occur on Yahoo quote endpoint; fallback below.
            continue

    if use_fallback:
        now = time.time()
        missing = [
            t for t in cleaned if t not in result and _FAILED_SYMBOLS.get(t, 0.0) <= now
        ]

        if missing:
            # Fallback 1: bulk 1-minute bars.
            try:
                hist = yf.download(
                    tickers=missing,
                    period="1d",
                    interval="1m",
                    progress=False,
                    auto_adjust=True,
                    threads=False,
                    group_by="ticker",
                )

                if hist is not None and not hist.empty:
                    if isinstance(hist.columns, pd.MultiIndex):
                        symbols_in_frame = set(hist.columns.get_level_values(0))
                        for ticker in missing:
                            if ticker not in symbols_in_frame:
                                continue
                            tdf = hist[ticker].copy()
                            close = tdf["Close"].dropna() if "Close" in tdf.columns else pd.Series(dtype=float)
                            if close.empty:
                                continue
                            last = float(close.iloc[-1])
                            prev = float(close.iloc[-2]) if len(close) > 1 else last
                            diff = last - prev
                            pct = (diff / prev * 100.0) if prev else 0.0
                            result[ticker] = {
                                "price": last,
                                "change": diff,
                                "change_percent": pct,
                                "timestamp": None,
                                "currency": None,
                                "source": "yfinance_1m_bulk",
                            }
                    else:
                        ticker = missing[0]
                        close = hist["Close"].dropna() if "Close" in hist.columns else pd.Series(dtype=float)
                        if not close.empty:
                            last = float(close.iloc[-1])
                            prev = float(close.iloc[-2]) if len(close) > 1 else last
                            diff = last - prev
                            pct = (diff / prev * 100.0) if prev else 0.0
                            result[ticker] = {
                                "price": last,
                                "change": diff,
                                "change_percent": pct,
                                "timestamp": None,
                                "currency": None,
                                "source": "yfinance_1m_bulk",
                            }
            except Exception:
                pass

            # Fallback 2: latest daily close for any symbol still missing.
            still_missing = [t for t in missing if t not in result]
            if still_missing:
                closes = fetch_bulk_last_close(still_missing, period="7d", interval="1d")
                for ticker, px in closes.items():
                    result[ticker] = {
                        "price": float(px),
                        "change": 0.0,
                        "change_percent": 0.0,
                        "timestamp": None,
                        "currency": None,
                        "source": "yfinance_1d_fallback",
                    }

            # Mark unresolved symbols in cooldown to avoid repeated hammering.
            for ticker in missing:
                if ticker not in result:
                    _FAILED_SYMBOLS[ticker] = time.time() + _FAIL_COOLDOWN_SEC

    # Mark any symbols still missing as temporarily failed to avoid repeated failures.
    for ticker in cleaned:
        if ticker not in result:
            _FAILED_SYMBOLS[ticker] = time.time() + _FAIL_COOLDOWN_SEC

    return result


def fetch_latest_price(ticker: str) -> float:
    """
    Fetch the latest price for `ticker`.
    Prefers Yahoo quote endpoint; falls back to recent yfinance bars.
    """
    symbol = normalize_ticker(ticker)
    live = fetch_live_quotes([symbol]).get(symbol)
    if live and live.get("price") is not None:
        return float(live["price"])

    df = yf.download(symbol, period="7d", interval="1d", progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise ValueError(f"No latest price data returned for ticker: {symbol}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = df["Close"].dropna()
    if close.empty:
        raise ValueError(f"No close price data returned for ticker: {symbol}")
    return float(close.iloc[-1])


def fetch_bulk_last_close(
    tickers: list[str],
    period: str = "7d",
    interval: str = "1d",
) -> dict[str, float]:
    """
    Fetch latest close for multiple symbols in one call.
    Returns a map: {SYMBOL: last_close}.
    """
    cleaned = normalize_tickers(tickers)
    if not cleaned:
        return {}

    out: dict[str, float] = {}
    try:
        df = yf.download(
            tickers=cleaned,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
            threads=False,
            group_by="ticker",
        )
        if df is None or df.empty:
            return out

        if isinstance(df.columns, pd.MultiIndex):
            level0 = set(df.columns.get_level_values(0))
            for sym in cleaned:
                if sym not in level0:
                    continue
                tdf = df[sym]
                close = tdf["Close"].dropna() if "Close" in tdf.columns else pd.Series(dtype=float)
                if close.empty:
                    continue
                out[sym] = float(close.iloc[-1])
        else:
            close = df["Close"].dropna() if "Close" in df.columns else pd.Series(dtype=float)
            if not close.empty:
                out[cleaned[0]] = float(close.iloc[-1])
    except Exception:
        return out

    return out
