"""
Paper trading engine.

State is persisted in SQLite (wallet table) and in-memory position data
that is rebuilt from trade history on startup.
"""

from __future__ import annotations

from threading import Lock

from database import get_wallet, update_wallet, record_trade, get_trades

STARTING_BALANCE = 100_000.0


class TradingEngine:
    def __init__(self):
        self._holdings: dict[str, float] = {}    # ticker -> signed quantity (+long, -short)
        self._cost_basis: dict[str, float] = {}  # ticker -> open position notional at entry
        self._lock = Lock()
        self._rebuild_holdings()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_holdings(self):
        """Reconstruct current holdings and open notional from trade history."""
        self._holdings = {}
        self._cost_basis = {}

        # get_trades is DESC; reverse to replay oldest -> newest
        for trade in reversed(get_trades(limit=5000)):
            asset = trade["asset"]
            decision = str(trade.get("decision", "")).upper()
            qty = float(trade.get("quantity") or 0.0)
            px = float(trade.get("price") or 0.0)

            held = self._holdings.get(asset, 0.0)
            cost = self._cost_basis.get(asset, 0.0)

            if decision == "BUY":
                if held < 0:
                    # BUY against an open short closes it in this engine.
                    self._holdings[asset] = 0.0
                    self._cost_basis[asset] = 0.0
                else:
                    self._holdings[asset] = held + qty
                    self._cost_basis[asset] = cost + (qty * px)

            elif decision == "SELL":
                if held > 0:
                    # SELL against an open long closes it in this engine.
                    self._holdings[asset] = 0.0
                    self._cost_basis[asset] = 0.0
                else:
                    # SELL while flat/short opens or adds short.
                    self._holdings[asset] = held - qty
                    self._cost_basis[asset] = cost + (qty * px)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def balance(self) -> float:
        return get_wallet()["balance"]

    @property
    def trade_count(self) -> int:
        return get_wallet()["trade_count"]

    def get_holdings(self) -> dict[str, float]:
        return dict(self._holdings)

    def get_position_details(self) -> dict[str, dict[str, float]]:
        details: dict[str, dict[str, float]] = {}
        for asset, qty in self._holdings.items():
            if abs(qty) <= 0:
                continue
            cost = self._cost_basis.get(asset, 0.0)
            abs_qty = abs(qty)
            details[asset] = {
                "quantity": qty,
                "cost_basis": cost,
                "avg_cost": (cost / abs_qty) if abs_qty > 0 else 0.0,
                "side": "LONG" if qty > 0 else "SHORT",
            }
        return details

    def reset_positions(self):
        with self._lock:
            self._holdings.clear()
            self._cost_basis.clear()

    def execute(
        self,
        asset: str,
        decision: str,
        price: float,
        confidence: int,
        reason: str,
        trade_amount: float = 10_000.0,
        style: str = "short_term",
        slippage_bps: float = 5.0,
        fee_bps: float = 2.0,
        fixed_fee_per_order: float = 0.0,
    ) -> dict:
        """Execute a paper trade and return a result dict."""
        with self._lock:
            wallet = get_wallet()
            balance = float(wallet["balance"])
            trade_count = int(wallet["trade_count"])

            held = float(self._holdings.get(asset, 0.0))
            decision = str(decision).upper()
            allow_short = (style or "").lower() == "day_trade"

            quantity = 0.0
            profit = 0.0
            fee_paid = 0.0
            skipped = False
            skip_reason = ""
            quoted_price = float(price)
            slippage = max(0.0, float(slippage_bps)) / 10_000.0
            fee_rate = max(0.0, float(fee_bps)) / 10_000.0
            fixed_fee = max(0.0, float(fixed_fee_per_order))
            exec_price = quoted_price

            if decision == "BUY":
                if held < 0:
                    # Cover full short.
                    cover_qty = abs(held)
                    exec_price = quoted_price * (1.0 + slippage)
                    cover_cost = cover_qty * exec_price
                    fee_paid = (cover_cost * fee_rate) + fixed_fee
                    if balance < (cover_cost + fee_paid):
                        skipped = True
                        skip_reason = (
                            f"Insufficient balance ({balance:.2f}) to cover short position in {asset}."
                        )
                    else:
                        quantity = cover_qty
                        short_entry_notional = self._cost_basis.get(asset, 0.0)
                        profit = short_entry_notional - cover_cost - fee_paid
                        balance -= (cover_cost + fee_paid)
                        self._holdings[asset] = 0.0
                        self._cost_basis[asset] = 0.0
                        trade_count += 1
                else:
                    exec_price = quoted_price * (1.0 + slippage)
                    fee_paid = (trade_amount * fee_rate) + fixed_fee
                    if balance < (trade_amount + fee_paid):
                        skipped = True
                        skip_reason = (
                            f"Insufficient balance ({balance:.2f}) for trade amount {trade_amount:.2f}"
                        )
                    else:
                        quantity = trade_amount / exec_price
                        spent = quantity * exec_price
                        balance -= (spent + fee_paid)
                        self._holdings[asset] = held + quantity
                        self._cost_basis[asset] = self._cost_basis.get(asset, 0.0) + spent
                        # Commission/slippage costs are realized immediately.
                        profit = -fee_paid
                        trade_count += 1

            elif decision == "SELL":
                if held > 0:
                    # Close full long.
                    exec_price = quoted_price * (1.0 - slippage)
                    quantity = held
                    proceeds = quantity * exec_price
                    fee_paid = (proceeds * fee_rate) + fixed_fee
                    open_cost = self._cost_basis.get(asset, 0.0)
                    profit = proceeds - open_cost - fee_paid
                    balance += (proceeds - fee_paid)
                    self._holdings[asset] = 0.0
                    self._cost_basis[asset] = 0.0
                    trade_count += 1
                elif allow_short:
                    # Open or add short in day-trade mode.
                    exec_price = quoted_price * (1.0 - slippage)
                    quantity = trade_amount / exec_price
                    proceeds = quantity * exec_price
                    fee_paid = (proceeds * fee_rate) + fixed_fee
                    balance += (proceeds - fee_paid)
                    self._holdings[asset] = held - quantity
                    self._cost_basis[asset] = self._cost_basis.get(asset, 0.0) + proceeds
                    profit = -fee_paid
                    trade_count += 1
                else:
                    skipped = True
                    skip_reason = f"No long holdings in {asset} to sell."

            else:  # HOLD
                pass

            if not skipped and decision in {"BUY", "SELL"}:
                update_wallet(balance, trade_count)
                record_trade(
                    asset=asset,
                    decision=decision,
                    price=exec_price,
                    quantity=quantity,
                    profit=profit,
                    reason=reason,
                    confidence=confidence,
                )

            holdings_snapshot = {
                k: round(v, 6) for k, v in self._holdings.items() if abs(v) > 0
            }

        return {
            "asset": asset,
            "decision": decision,
            "price": round(exec_price, 4),
            "quoted_price": round(quoted_price, 4),
            "quantity": round(quantity, 6),
            "profit": round(profit, 2),
            "fee_paid": round(fee_paid, 2),
            "wallet_balance": round(balance, 2),
            "holdings": holdings_snapshot,
            "confidence": confidence,
            "reason": reason,
            "trade_count": trade_count,
            "skipped": skipped,
            "skip_reason": skip_reason,
        }


# Module-level singleton so all routes share the same engine state
_engine: TradingEngine | None = None


def get_engine() -> TradingEngine:
    global _engine
    if _engine is None:
        _engine = TradingEngine()
    return _engine
