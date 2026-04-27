"""Helpers for normalizing ticker symbols across the app."""

from __future__ import annotations


def normalize_ticker(symbol: str) -> str:
    """
    Normalize one ticker symbol.
    - Trim spaces
    - Uppercase
    - Remove leading '$' (common from copied symbols)
    - Remove inner spaces
    """
    sym = str(symbol or "").strip().upper().replace(" ", "")
    while sym.startswith("$"):
        sym = sym[1:]
    return sym


def normalize_tickers(symbols: list[str]) -> list[str]:
    """Normalize and deduplicate symbols while preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        sym = normalize_ticker(symbol)
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out
