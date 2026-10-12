"""Exportação e gravação contínua do histórico de coortes da Coinversa (Hyperliquid).

A API guarda só uma janela móvel de ~90 dias: o que não for copiado se perde. Este módulo
copia tudo para SQLite local; um cron diário (janela de 3 dias) continua a cópia sem perder horas.

Fatos confirmados na API (12/10/2026, plano Pro):
- `since` só aceita formato relativo ("7d", "90d", "3h"); ms e ISO dão HTTP 500.
- "90d" funciona numa chamada (~68 mil linhas por moeda); o dado mais antigo era 2026-07-14.
- cada hora tem 32 linhas: tierType pnl/size/pnl_recent/size_recent x 8 grupos.
- netBias nesta rota vem em %. Os notionals ficam gravados para recalcular (L−S)/(L+S).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from bot.logging_setup import get_logger

log = get_logger("onchain.cohort_history")

USER_AGENT = "bybit-scanner-bot/0.1"


# ---------------------------------------------------------------------------- mapeamento de símbolos
@dataclass(frozen=True)
class CoinPair:
    bybit_symbol: str
    hl_coin: str
    mult: int  # preço HL ÷ mult = preço Bybit (k = 1000 unidades)


def hl_coin_for(base: str, symbol_map: Any) -> tuple[str, int] | None:
    """Coin da Hyperliquid para a moeda base da Bybit, ou None se negada/desligada."""
    base = base.upper()
    if base in {d.upper() for d in symbol_map.deny}:
        return None
    override = symbol_map.overrides.get(base)
    if override is not None:
        return override.hl, override.mult
    return (base, 1) if symbol_map.auto_native else None


def is_crypto_hl_coin(coin: str, patterns: Iterable[str]) -> bool:
    """Exclui builder dexes (ações/FX), HIP-4 e spot interno da HL."""
    return not any(p in coin for p in patterns)


def select_pairs(
    bybit_tickers: dict[str, dict[str, Any]],
    registry: Any,          # InstrumentRegistry
    universe: Any,          # UniverseConfig
    symbol_map: Any,        # OnchainSymbolMap
    hl_markets: list[dict[str, Any]],
    always: Iterable[str] = ("BTCUSDT",),
) -> list[CoinPair]:
    """Pares spot/USDT da Bybit elegíveis que têm perpétuo nativo na HL com preço compatível."""
    hl = {}
    for market in hl_markets:
        coin = market.get("coin", "")
        # perps nativos vêm com dex = "hl" (confirmado); os demais são builder dexes (ações, FX...)
        if market.get("dex") != symbol_map.native_dex or not is_crypto_hl_coin(coin, symbol_map.exclude_hl_patterns):
            continue
        hl[coin] = market
    excluded = {b.upper() for b in universe.exclude_bases} | {b.upper() for b in universe.blacklist}
    always = set(always)
    pairs: list[CoinPair] = []
    for symbol, ticker in bybit_tickers.items():
        if symbol not in registry:
            continue
        rules = registry.get(symbol)
        base = rules.base_coin.upper()
        if not rules.trading or base in excluded or symbol in universe.blacklist:
            continue
        if any(base.endswith(s.upper()) for s in universe.exclude_suffixes):
            continue
        turnover = float(ticker.get("turnover24h") or 0)
        if turnover < universe.min_turnover_24h_usdt and symbol not in always:
            continue
        mapped = hl_coin_for(base, symbol_map)
        if mapped is None or mapped[0] not in hl:
            continue
        hl_coin, mult = mapped
        hl_price = float(hl[hl_coin].get("markPx") or 0) / mult
        bybit_price = float(ticker.get("lastPrice") or 0)
        if hl_price <= 0 or bybit_price <= 0:
            continue
        deviation = abs(hl_price / bybit_price - 1) * 100
        if deviation > symbol_map.price_check_max_dev_pct:
            log.warning("preço HL incompatível com a Bybit, par ignorado",
                        extra={"symbol": symbol, "data": {"hl_coin": hl_coin, "desvio_pct": round(deviation, 2)}})
            continue
        pairs.append(CoinPair(symbol, hl_coin, mult))
    return sorted(pairs, key=lambda p: (p.bybit_symbol not in always, p.bybit_symbol))


# ---------------------------------------------------------------------------- cliente HTTP
class CoinversaError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class CoinversaClient:
    """Cliente mínimo e só de leitura (GET), com espaçamento e respeito ao limite da API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        auth_header: str = "X-API-Key",
        timeout_seconds: float = 60,
        min_interval_ms: int = 1300,
        max_retries: int = 3,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = http_client or httpx.Client(timeout=timeout_seconds)
        self._headers = {auth_header: api_key, "User-Agent": USER_AGENT}
        self._interval = min_interval_ms / 1000
        self._max_retries = max_retries
        self._sleep = sleep
        self._monotonic = monotonic
        self._clock = clock
        self._next_at = 0.0

    def close(self) -> None:
        self._http.close()

    def _pace(self) -> None:
        wait = self._next_at - self._monotonic()
        if wait > 0:
            self._sleep(wait)
        self._next_at = self._monotonic() + self._interval

    def get(self, path: str, **params: Any) -> Any:
        for attempt in range(self._max_retries + 1):
            self._pace()
            try:
                response = self._http.get(self.base_url + path, params=params or None, headers=self._headers)
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise CoinversaError(f"falha de rede em {path}: {type(exc).__name__}") from exc
                self._sleep(2**attempt)
                continue
            if response.status_code == 429 and attempt < self._max_retries:
                self._sleep(self._retry_after(response))
                continue
            if response.status_code >= 500 and attempt < self._max_retries:
                self._sleep(2**attempt)
                continue
            if response.status_code != 200:
                raise CoinversaError(f"HTTP {response.status_code} em {path}: {response.text[:200]}",
                                     response.status_code)
            remaining = response.headers.get("x-ratelimit-remaining")
            reset = response.headers.get("x-ratelimit-reset")
            if remaining == "0" and reset and reset.isdigit():
                self._sleep(max(0.0, int(reset) - self._clock()) + 0.5)
            return response.json()
        raise CoinversaError(f"tentativas esgotadas em {path}")

    def _retry_after(self, response: httpx.Response) -> float:
        header = response.headers.get("retry-after")
        if header and header.replace(".", "", 1).isdigit():
            return float(header)
        try:
            return float(response.json().get("retryAfterSeconds", 5))
        except (ValueError, AttributeError):
            return 5.0

    def market_overview(self) -> list[dict[str, Any]]:
        return self.get("/pulse/market-overview").get("markets", [])

    def cohort_history(self, coin: str, since: str) -> list[dict[str, Any]]:
        body = self.get("/pulse/cohort-bias/history", coin=coin, since=since)
        if isinstance(body, list):
            return body
        return next((v for v in body.values() if isinstance(v, list)), [])


# ---------------------------------------------------------------------------- armazenamento
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cohort_history (
    coin           TEXT    NOT NULL,
    tier_type      TEXT    NOT NULL,
    tier           TEXT    NOT NULL,
    ts             INTEGER NOT NULL,
    long_notional  REAL,
    short_notional REAL,
    net_bias_pct   REAL,
    account_count  INTEGER,
    fetched_at     INTEGER NOT NULL,
    PRIMARY KEY (coin, tier_type, tier, ts)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS export_runs (
    run_at   INTEGER NOT NULL,
    since    TEXT    NOT NULL,
    coins    INTEGER NOT NULL,
    rows     INTEGER NOT NULL,
    failures TEXT    NOT NULL
);
"""


class CohortHistoryStore:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def upsert(self, rows: Iterable[dict[str, Any]], fetched_at_ms: int) -> int:
        values = []
        for r in rows:
            try:
                values.append((r["coin"], r["tierType"], r["tier"], int(r["timestamp"]), r.get("longNotional"),
                               r.get("shortNotional"), r.get("netBias"), r.get("accountCount"), fetched_at_ms))
            except (KeyError, TypeError, ValueError):
                continue
        if not values:
            return 0
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO cohort_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        return len(values)

    def record_run(self, run_at_ms: int, since: str, coins: int, rows: int, failures: list[str]) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO export_runs VALUES (?, ?, ?, ?, ?)",
                               (run_at_ms, since, coins, rows, ",".join(failures)))

    def coverage(self) -> list[tuple[str, int, int, int]]:
        """[(coin, primeiro ts, último ts, horas distintas)]."""
        with self._lock:
            return self._conn.execute(
                "SELECT coin, MIN(ts), MAX(ts), COUNT(DISTINCT ts) FROM cohort_history GROUP BY coin ORDER BY coin"
            ).fetchall()


def export_history(client: CoinversaClient, store: CohortHistoryStore, pairs: list[CoinPair], since: str,
                   now_ms: Callable[[], int] = lambda: int(time.time() * 1000)) -> dict[str, Any]:
    """Baixa `since` de histórico de cada coin e grava. Uma moeda com erro não para as outras."""
    total, failures = 0, []
    for pair in pairs:
        try:
            rows = client.cohort_history(pair.hl_coin, since)
            if not rows:
                log.warning("histórico vazio (conta como ausente)", extra={"symbol": pair.bybit_symbol})
            total += store.upsert(rows, now_ms())
        except CoinversaError as exc:
            failures.append(pair.hl_coin)
            log.error("falha ao exportar histórico", extra={"symbol": pair.bybit_symbol,
                                                            "data": {"hl_coin": pair.hl_coin, "error": str(exc)}})
    store.record_run(now_ms(), since, len(pairs), total, failures)
    return {"coins": len(pairs), "rows": total, "failures": failures}
