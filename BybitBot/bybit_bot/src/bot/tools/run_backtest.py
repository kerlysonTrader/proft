"""Roda o backtest com o histórico baixado e gera o relatório do Gate 5.

    python -m bot.tools.run_backtest                                   # todos os setups do config
    python -m bot.tools.run_backtest --setups pullback_tendencia --label so_pullback
    python -m bot.tools.run_backtest --exit-mode fixed_tp2 --label tp2_fixo

Lê market_data.history.db_path (python -m bot.backtest.data_loader). Grava o relatório em
reports/<data>_<label>.md e os trades/patrimônio em data/backtest/<label>_*.csv.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime

from bot.backtest.engine import Backtester, load_symbol
from bot.backtest.report import Metrics, gate_checks, render_markdown, trades_frame
from bot.backtest.walk_forward import walk_forward_windows
from bot.config import PROJECT_ROOT, load_config, resolve_path
from bot.logging_setup import setup_logging
from bot.storage.kline_store import KlineStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest do robô (Fase 5)")
    parser.add_argument("--setups", default=None, help="lista separada por vírgula (padrão: setups.enabled)")
    parser.add_argument("--exit-mode", choices=["trailing", "fixed_tp2"], default=None)
    parser.add_argument("--label", default="completo")
    parser.add_argument("--symbols", default=None, help="restringe a estas moedas (BTC sempre entra)")
    parser.add_argument("--no-kill-switch", action="store_true",
                        help="PESQUISA: desliga o kill switch para ver o período inteiro (nunca no robô real)")
    parser.add_argument("--no-invalidation", action="store_true", help="desliga a saída por fechamento 4H < EMA50")
    parser.add_argument("--intraday", action="store_true",
                        help="perfil intraday: gatilho 15m, contexto 1H (precisa das velas de 15m no histórico)")
    parser.add_argument("--time-stop-hours", type=float, default=None, help="horas máximas sem chegar a +0,5R")
    parser.add_argument("--min-stop-pct", type=float, default=None, help="distância mínima do stop (%%)")
    args = parser.parse_args(argv)

    config = load_config()
    if args.intraday:
        config = config.model_copy(update={"setups": config.setups.model_copy(
            update={"trigger_interval": "15", "context_interval": "60"})})
    if args.time_stop_hours is not None:
        config = config.model_copy(update={"exits": config.exits.model_copy(
            update={"time_stop_hours": args.time_stop_hours})})
    if args.min_stop_pct is not None:
        config = config.model_copy(update={"setups": config.setups.model_copy(update={
            "common": config.setups.common.model_copy(update={"min_stop_pct": args.min_stop_pct})})})
    if args.setups:
        config = config.model_copy(update={"setups": config.setups.model_copy(
            update={"enabled": [s.strip() for s in args.setups.split(",")]})})
    if args.exit_mode:
        config = config.model_copy(update={"exits": config.exits.model_copy(update={"mode_after_tp1": args.exit_mode})})
    if args.no_kill_switch:
        config = config.model_copy(update={"risk": config.risk.model_copy(update={"max_drawdown_from_peak_pct": 100})})
    if args.no_invalidation:
        config = config.model_copy(update={"exits": config.exits.model_copy(
            update={"invalidation_close_below_ema50_4h": False})})
    setup_logging("WARNING")

    db_path = resolve_path(config.market_data.history.db_path)
    store = KlineStore(db_path)
    selection = db_path.with_name("history_symbols.json")
    symbols = [s["symbol"] for s in json.loads(selection.read_text(encoding="utf-8"))["symbols"]] \
        if selection.exists() else store.symbols("60")
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(",")}
        symbols = [s for s in symbols if s in wanted or s == config.regime.btc_symbol]
    btc = config.regime.btc_symbol

    t0 = time.monotonic()
    data = {}
    btc_data = load_symbol(store, btc, "BTC", None, config)
    if btc_data is None:
        print("Sem histórico do BTC: rode python -m bot.backtest.data_loader")
        return 1
    data[btc] = btc_data
    for sym in symbols:
        if sym == btc:
            continue
        sd = load_symbol(store, sym, sym.removesuffix(config.bybit.quote), btc_data.d1, config)
        if sd is not None:
            data[sym] = sd
    store.close()
    first = int(btc_data.h1["start_ms"].iloc[0]) + config.backtest.warmup_days * 86_400_000
    last = int(btc_data.h1["start_ms"].iloc[-1]) + 3_600_000
    print(f"{len(data)} moedas carregadas em {time.monotonic() - t0:.0f} s; simulando "
          f"{datetime.fromtimestamp(first / 1000, UTC):%d/%m/%Y} a {datetime.fromtimestamp(last / 1000, UTC):%d/%m/%Y}"
          f" | setups: {', '.join(config.setups.enabled)} | saída após TP1: {config.exits.mode_after_tp1}")

    def progress(n: int, total: int) -> None:
        print(f"  {n / total * 100:5.1f}% ({time.monotonic() - t0:.0f} s)", flush=True)

    result = Backtester(config, data, first, last, progress=progress).run()
    windows = walk_forward_windows(result, config.backtest.walk_forward)
    report = render_markdown(result, config, windows, title=f"Backtest — {args.label}")

    stamp = datetime.now(UTC).strftime("%Y%m%d")
    report_path = PROJECT_ROOT / "reports" / f"{stamp}_{args.label}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    out_dir = resolve_path("data/backtest")
    out_dir.mkdir(parents=True, exist_ok=True)
    trades_frame(result.trades).to_csv(out_dir / f"{args.label}_trades.csv", index=False)
    result.equity.rename("equity").to_csv(out_dir / f"{args.label}_equity.csv", index_label="ts_ms")

    m = Metrics.of(result.trades)
    checks = gate_checks(result, config.backtest.gate, windows)
    print(f"\nTrades {m.trades} | acerto {m.win_rate:.1f}% | expectância {m.expectancy_r:.3f} R | "
          f"PF {m.profit_factor:.2f} | resultado {m.pnl:.2f} USDT | tempo {time.monotonic() - t0:.0f} s")
    for c in checks:
        print(f"  [{'OK' if c.passed else 'X '}] {c.name}: {c.value}")
    print(f"Gate 5: {'APROVADO' if all(c.passed for c in checks) else 'REPROVADO'} — relatório em {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
