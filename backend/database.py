import sqlite3
import os
from pathlib import Path
from datetime import datetime, timezone

_DEFAULT_DB_PATH = Path(__file__).parent / "trades.db"
DB_PATH = Path(os.getenv("TRADES_DB_PATH", str(_DEFAULT_DB_PATH))).expanduser()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                asset     TEXT    NOT NULL,
                decision  TEXT    NOT NULL,
                price     REAL    NOT NULL,
                quantity  REAL    NOT NULL DEFAULT 0,
                profit    REAL    NOT NULL DEFAULT 0,
                reason    TEXT,
                confidence INTEGER,
                timestamp TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet (
                id            INTEGER PRIMARY KEY CHECK (id = 1),
                balance       REAL NOT NULL DEFAULT 100000,
                trade_count   INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rule_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                asset       TEXT,
                event_type  TEXT NOT NULL,
                decision    TEXT,
                reason      TEXT,
                source      TEXT,
                confidence  INTEGER,
                timestamp   TEXT NOT NULL
            )
        """)
        # Ensure the single wallet row exists
        conn.execute("""
            INSERT OR IGNORE INTO wallet (id, balance, trade_count)
            VALUES (1, 100000, 0)
        """)
        conn.commit()


def record_trade(asset: str, decision: str, price: float, quantity: float,
                 profit: float, reason: str, confidence: int):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO trades (asset, decision, price, quantity, profit, reason, confidence, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (asset, decision, price, quantity, profit, reason, confidence,
              datetime.now(timezone.utc).isoformat()))
        conn.commit()


def get_trades(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_wallet() -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM wallet WHERE id = 1").fetchone()
    return dict(row) if row else {"balance": 100000, "trade_count": 0}


def record_rule_log(
    asset: str,
    event_type: str,
    decision: str | None,
    reason: str,
    source: str = "manual",
    confidence: int | None = None,
):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO rule_logs (asset, event_type, decision, reason, source, confidence, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset,
                event_type,
                decision,
                reason,
                source,
                confidence,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def get_rule_logs(limit: int = 100) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM rule_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_wallet(balance: float, trade_count: int):
    with get_connection() as conn:
        conn.execute("""
            UPDATE wallet SET balance = ?, trade_count = ? WHERE id = 1
        """, (balance, trade_count))
        conn.commit()


def reset_wallet():
    with get_connection() as conn:
        conn.execute("UPDATE wallet SET balance = 100000, trade_count = 0 WHERE id = 1")
        conn.execute("DELETE FROM trades")
        conn.execute("DELETE FROM rule_logs")
        conn.commit()
