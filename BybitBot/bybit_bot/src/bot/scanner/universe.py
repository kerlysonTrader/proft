"""Universo de moedas (seção 1 do 03_ESTRATEGIA.md).

Filtros baratos primeiro, com 1 chamada (tickers) + regras de instrumento:
par USDT em negociação, exclusões, liquidez 24h, spread e variação 24h.
O histórico mínimo (velas diárias) é checado quando as velas são baixadas e a
profundidade do livro só para os finalistas (ver scanner.py).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UniverseCoin:
    symbol: str
    base: str
    price: float
    change_24h_pct: float
    turnover_24h_usdt: float
    spread_pct: float


@dataclass
class UniverseResult:
    coins: list[UniverseCoin]
    rejected: Counter = field(default_factory=Counter)  # motivo -> quantidade


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def spread_pct(bid: float | None, ask: float | None) -> float | None:
    """(ask − bid) / preço médio, em %."""
    if not bid or not ask or bid <= 0 or ask <= 0:
        return None
    return (ask - bid) / ((ask + bid) / 2) * 100


def build_universe(tickers: dict[str, dict[str, Any]], registry: Any, universe: Any, quote: str = "USDT",
                   always: tuple[str, ...] = ()) -> UniverseResult:
    """Aplica os filtros de universo. `always` (ex.: BTC) ignora liquidez/variação, nunca as exclusões."""
    excluded = {b.upper() for b in universe.exclude_bases}
    blacklist = {b.upper() for b in universe.blacklist}
    result = UniverseResult(coins=[])

    for symbol, t in tickers.items():
        if not symbol.endswith(quote) or symbol not in registry:
            result.rejected["fora da lista de pares USDT"] += 1
            continue
        rules = registry.get(symbol)
        base = rules.base_coin.upper()
        if not rules.trading:
            result.rejected["par fora de negociação"] += 1
            continue
        if base in excluded or base in blacklist or symbol.upper() in blacklist:
            result.rejected["excluída (stable/atrelada/lista negra)"] += 1
            continue
        if any(base.endswith(s.upper()) for s in universe.exclude_suffixes):
            result.rejected["token alavancado"] += 1
            continue

        price = _float(t.get("lastPrice"))
        turnover = _float(t.get("turnover24h")) or 0.0
        change = _float(t.get("price24hPcnt"))
        change_pct = change * 100 if change is not None else None  # a Bybit manda fração (0.0123 = 1,23 %)
        spread = spread_pct(_float(t.get("bid1Price")), _float(t.get("ask1Price")))
        if price is None or price <= 0 or change_pct is None:
            result.rejected["ticker incompleto"] += 1
            continue

        forced = symbol in always
        if not forced:
            if turnover < universe.min_turnover_24h_usdt:
                result.rejected["liquidez 24h baixa"] += 1
                continue
            if spread is None or spread > universe.max_spread_pct:
                result.rejected["spread alto"] += 1
                continue
            if change_pct > universe.max_change_24h_pct:
                result.rejected["já esticada (alta 24h)"] += 1
                continue
            if change_pct < universe.min_change_24h_pct:
                result.rejected["queda forte 24h"] += 1
                continue
        result.coins.append(UniverseCoin(symbol, base, price, change_pct, turnover,
                                         spread if spread is not None else float("nan")))

    result.coins.sort(key=lambda c: c.turnover_24h_usdt, reverse=True)
    return result
