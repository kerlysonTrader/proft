"""Persistência de velas FECHADAS em SQLite (histórico para scanner e backtest)."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from bot.bybit.client import Kline

_SCHEMA = """
CREATE TABLE IF NOT EXISTS klines (
    symbol   TEXT    NOT NULL,
    interval TEXT    NOT NULL,
    start_ms INTEGER NOT NULL,
    open     REAL    NOT NULL,
    high     REAL    NOT NULL,
    low      REAL    NOT NULL,
    close    REAL    NOT NULL,
    volume   REAL    NOT NULL,
    turnover REAL    NOT NULL,
    PRIMARY KEY (symbol, interval, start_ms)
) WITHOUT ROWID;
"""


class KlineStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def upsert(self, klines: Iterable[Kline]) -> int:
        rows = [(k.symbol, k.interval, k.start_ms, k.open, k.high, k.low, k.close, k.volume, k.turnover)
                for k in klines]
        if not rows:
            return 0
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO klines VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        return len(rows)

    def load(self, symbol: str, interval: str, start_ms: int | None = None, end_ms: int | None = None
             ) -> list[Kline]:
        """Velas em ordem cronológica com start_ms em [start_ms, end_ms]."""
        sql = "SELECT start_ms, open, high, low, close, volume, turnover FROM klines WHERE symbol=? AND interval=?"
        params: list[object] = [symbol, interval]
        if start_ms is not None:
            sql += " AND start_ms >= ?"
            params.append(start_ms)
        if end_ms is not None:
            sql += " AND start_ms <= ?"
            params.append(end_ms)
        sql += " ORDER BY start_ms"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [Kline(r[0], interval, r[1], r[2], r[3], r[4], r[5], r[6], symbol) for r in rows]

    def bounds(self, symbol: str, interval: str) -> tuple[int | None, int | None, int]:
        """(primeiro start_ms, último start_ms, quantidade)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(start_ms), MAX(start_ms), COUNT(*) FROM klines WHERE symbol=? AND interval=?",
                (symbol, interval)).fetchone()
        return row[0], row[1], row[2]

    def symbols(self, interval: str | None = None) -> list[str]:
        sql = "SELECT DISTINCT symbol FROM klines" + (" WHERE interval=?" if interval else "") + " ORDER BY symbol"
        with self._lock:
            return [r[0] for r in self._conn.execute(sql, (interval,) if interval else ()).fetchall()]
