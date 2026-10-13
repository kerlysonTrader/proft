"""Grava config/backtest_stats.json: a estatística dos backtests que acompanha os planos no painel.

    python -m bot.tools.build_backtest_stats

Fica na pasta config para ir junto com o código para a VM (os CSVs de data/backtest só existem no PC).
Rode de novo sempre que refizer os backtests de referência.
"""

from __future__ import annotations

import sys

from bot.config import load_config, resolve_path
from bot.markets.stats import STATS_FILE, save_stats_file


def main() -> int:
    config = load_config()
    sources = {f"mt5_{group}_{side}": resolve_path(f"data/backtest/mt5_{group}_{side}_trades.csv")
               for group in config.markets.mt5.groups for side in ("long", "short")}
    sources["cripto_spot_long"] = resolve_path("data/backtest/intraday_stop08_trades.csv")    # 15m/1H, stop ≥ 0,8 %
    sources["cripto_perp_long"] = resolve_path("data/backtest/perp_intraday_long_trades.csv")
    sources["cripto_perp_short"] = resolve_path("data/backtest/perp_intraday_short_trades.csv")
    counts = save_stats_file(resolve_path(STATS_FILE), sources)
    for key, n in counts.items():
        print(f"  {key:<20} {n:>5} trades" if n else f"  {key:<20} sem backtest")
    print(f"Gravado em {resolve_path(STATS_FILE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
