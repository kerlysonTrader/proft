"""Baixa o histórico de velas para o backtest (Fase 5).

    python -m bot.backtest.data_loader [--months 13] [--top-n 50] [--intervals 60,240,D]

Escolhe as `top_n` moedas spot/USDT de maior volume 24h (sem stablecoins, tokens alavancados,
wrapped e lista negra do config), sempre inclui o BTC, e grava as velas FECHADAS em SQLite
(market_data.history.db_path). Só usa dados públicos: não precisa de chave nem do IP da VM.
Rodar de novo só baixa o que falta.

Atenção (viés de sobrevivência): a lista é das maiores moedas de HOJE. Moedas que eram grandes
no passado e caíram não entram. O relatório do backtest deve citar essa limitação.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Any

from bot.bybit.client import KLINE_INTERVAL_MS, BybitClient
from bot.bybit.instruments import InstrumentRegistry
from bot.config import load_config, resolve_path
from bot.data.market_data import MarketData
from bot.logging_setup import get_logger, setup_logging
from bot.storage.kline_store import KlineStore

log = get_logger("backtest.data_loader")

DAY_MS = 86_400_000
MONTH_MS = 30 * DAY_MS


def select_top_symbols(
    tickers: dict[str, dict[str, Any]],
    registry: InstrumentRegistry,
    universe: Any,  # bot.config.UniverseConfig
    top_n: int,
    btc_symbol: str,
) -> list[tuple[str, float]]:
    """[(símbolo, turnover24h)] das maiores moedas elegíveis, BTC primeiro."""
    excluded = {b.upper() for b in universe.exclude_bases}
    blacklist = {b.upper() for b in universe.blacklist}
    candidates: list[tuple[str, float]] = []
    for symbol, ticker in tickers.items():
        if symbol not in registry:
            continue
        rules = registry.get(symbol)
        base = rules.base_coin.upper()
        if not rules.trading or base in excluded or base in blacklist or symbol in blacklist:
            continue
        if any(base.endswith(suffix.upper()) for suffix in universe.exclude_suffixes):
            continue
        try:
            turnover = float(ticker.get("turnover24h") or 0)
        except ValueError:
            continue
        candidates.append((symbol, turnover))
    candidates.sort(key=lambda item: item[1], reverse=True)
    selected = [c for c in candidates if c[0] != btc_symbol][: max(top_n - 1, 0)]
    btc = next((c for c in candidates if c[0] == btc_symbol), (btc_symbol, 0.0))
    return [btc, *selected]


def download_symbol(md: MarketData, store: KlineStore, symbol: str, interval: str, start_ms: int,
                    now_ms: int) -> dict[str, Any]:
    """Baixa [start_ms, última vela fechada]; se já houver dados cobrindo o início, só o final."""
    step = KLINE_INTERVAL_MS[interval]
    last_closed = md.last_closed_start(interval, now_ms)
    first, last, _ = store.bounds(symbol, interval)
    fetch_from = start_ms
    if first is not None and first <= start_ms + step and last is not None:
        fetch_from = last + step
    fetched = []
    if fetch_from <= last_closed:
        fetched = [k for k in md.fetch_range(symbol, interval, fetch_from, last_closed) if k.end_ms <= now_ms]
        store.upsert(fetched)
    first, last, count = store.bounds(symbol, interval)
    return {"symbol": symbol, "interval": interval, "new": len(fetched), "count": count, "first_ms": first,
            "last_ms": last}


def _date(ms: int | None) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d") if ms else "-"


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    hist = config.market_data.history
    parser = argparse.ArgumentParser(description="Baixa o histórico de velas para o backtest")
    parser.add_argument("--months", type=int, default=hist.months)
    parser.add_argument("--top-n", type=int, default=hist.top_n)
    parser.add_argument("--intervals", default=",".join(hist.intervals))
    parser.add_argument("--db", default=hist.db_path)
    args = parser.parse_args(argv)
    setup_logging(config.logging.level)

    intervals = [i.strip() for i in args.intervals.split(",") if i.strip()]
    db_path = resolve_path(args.db)
    client = BybitClient.from_config(config, secrets=None, mode="paper")  # só dados públicos
    md = MarketData(client, config.market_data)
    store = KlineStore(db_path)

    registry = InstrumentRegistry.load(client, quote=config.bybit.quote)
    chosen = select_top_symbols(md.spot_tickers(), registry, config.universe, args.top_n,
                                config.regime.btc_symbol)
    client.sync_time()
    now_ms = client.now_ms()
    start_ms = now_ms - args.months * MONTH_MS
    log.info("download iniciado", extra={"data": {"moedas": len(chosen), "intervalos": intervals,
                                                  "inicio": _date(start_ms), "db": str(db_path)}})

    rows = []
    for symbol, _turnover in chosen:
        for interval in intervals:
            try:
                rows.append(download_symbol(md, store, symbol, interval, start_ms, now_ms))
            except Exception as exc:  # uma moeda com problema não derruba o download
                log.error("falha no download", extra={"symbol": symbol,
                                                      "data": {"interval": interval, "error": str(exc)}})
                rows.append({"symbol": symbol, "interval": interval, "new": 0, "count": 0, "first_ms": None,
                             "last_ms": None, "error": str(exc)})

    selection_path = db_path.with_name("history_symbols.json")
    selection_path.write_text(json.dumps({
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "criterion": f"top {args.top_n} por turnover24h spot/USDT no dia do download (viés de sobrevivência)",
        "symbols": [{"symbol": s, "turnover24h": t} for s, t in chosen],
    }, indent=2), encoding="utf-8")

    full_year = now_ms - 12 * MONTH_MS
    short = sorted({r["symbol"] for r in rows if r["first_ms"] and r["first_ms"] > full_year})
    failed = sorted({r["symbol"] for r in rows if r.get("error")})
    print(f"\n===== HISTÓRICO ({db_path}) =====")
    print(f"{'símbolo':<14}{'interv.':>8}{'velas':>8}{'novas':>8}  início      fim")
    for r in rows:
        print(f"{r['symbol']:<14}{r['interval']:>8}{r['count']:>8}{r['new']:>8}  {_date(r['first_ms'])}  "
              f"{_date(r['last_ms'])}")
    print(f"\nMoedas: {len(chosen)} | com menos de 12 meses de histórico: {len(short)} {short}")
    print(f"Falhas: {failed or 'nenhuma'} | lista salva em {selection_path.name}")
    store.close()
    client.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
