"""Baixa do MT5 aberto (SOMENTE LEITURA) o histórico dos ativos de markets.mt5.groups.

    python -m bot.tools.mt5_history                 # todos os grupos, 15m/1H/4H/1D, até max_bars velas
    python -m bot.tools.mt5_history --intervals 15  # só 15m

Grava em markets.mt5.history_db e o resumo (grupo, dígitos, spread típico) em <db>_symbols.json.
Roda no PC (Windows) com o MT5 da corretora aberto e conectado.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from bot.config import load_config, resolve_path
from bot.logging_setup import setup_logging
from bot.markets.mt5_source import Mt5Error, Mt5Reader
from bot.storage.kline_store import KlineStore


def _date(ms: int | None) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d") if ms else "-"


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    cfg = config.markets.mt5
    parser = argparse.ArgumentParser(description="Histórico do MT5 (somente leitura)")
    parser.add_argument("--intervals", default="15,60,240,D")
    args = parser.parse_args(argv)
    setup_logging("WARNING")
    intervals = [i.strip() for i in args.intervals.split(",") if i.strip()]
    db_path = resolve_path(cfg.history_db)
    store = KlineStore(db_path)
    symbols = [(group, s) for group, names in cfg.groups.items() for s in names]
    summary, failures = [], []
    with Mt5Reader(cfg.server_utc_offset_hours, cfg.max_bars) as reader:
        info = reader.describe()
        offset = reader.detect_offset([s for _, s in symbols])
        print(f"MT5: {info['server']} ({info['company']}) | demo={info['demo']} | fuso UTC{offset:+d} | "
              f"máx. barras {info['maxbars']}")
        for group, symbol in symbols:
            meta = reader.meta(symbol)
            if meta is None:
                failures.append(symbol)
                print(f"  {symbol}: não existe neste servidor")
                continue
            row = {"symbol": symbol, "group": group, "digits": meta.digits, "point": meta.point,
                   "spread_points": meta.spread_points, "spread_pct": meta.spread_pct()}
            for interval in intervals:
                try:
                    klines = reader.rates(symbol, interval)
                except Mt5Error as exc:
                    failures.append(f"{symbol}:{interval}")
                    print(f"  {symbol} {interval}: {exc}")
                    continue
                store.upsert(klines)
                first, last, count = store.bounds(symbol, interval)
                row[interval] = {"count": count, "first": _date(first), "last": _date(last)}
            summary.append(row)
            parts = " | ".join(f"{i}: {row[i]['count']} ({row[i]['first']})" for i in intervals if i in row)
            print(f"  {group:<8} {symbol:<10} spread {row['spread_pct']:.3f}% | {parts}")
    store.close()
    db_path.with_name(f"{db_path.stem}_symbols.json").write_text(json.dumps({
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "server": info["server"],
        "offset_hours": offset, "symbols": summary}, indent=2), encoding="utf-8")
    print(f"Falhas: {failures or 'nenhuma'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
