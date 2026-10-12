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
from bot.data.market_data import klines_to_frame
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
    parser.add_argument("--max-stop-pct", type=float, default=None, help="distância máxima do stop (%%)")
    parser.add_argument("--market", choices=["spot", "perp", "mt5"], default="spot",
                        help="spot (Bybit), perp (perpétuos Bybit) ou mt5 (ativos da corretora)")
    parser.add_argument("--group", default=None, help="grupo do MT5 (metais, forex, indices, energia)")
    parser.add_argument("--short", action="store_true", help="estuda as VENDAS (gráfico invertido)")
    parser.add_argument("--fee-rate", type=float, default=None, help="custo por lado (fração), sobrepõe o do mercado")
    args = parser.parse_args(argv)

    config = load_config()
    if args.intraday:
        config = config.model_copy(update={"setups": config.setups.model_copy(
            update={"trigger_interval": "15", "context_interval": "60"})})
    if args.time_stop_hours is not None:
        config = config.model_copy(update={"exits": config.exits.model_copy(
            update={"time_stop_hours": args.time_stop_hours})})
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

    # ---------------------------------------------------------------- mercado
    fees: dict[str, float] = {}
    if args.market == "mt5":
        mcfg = config.markets.mt5
        if not args.group or args.group not in mcfg.groups:
            print(f"Informe --group entre: {', '.join(mcfg.groups)}")
            return 1
        db_path = resolve_path(mcfg.history_db)
        meta = json.loads(db_path.with_name(f"{db_path.stem}_symbols.json").read_text(encoding="utf-8"))["symbols"]
        meta = [m for m in meta if m["group"] == args.group]
        symbols = [m["symbol"] for m in meta]
        # custo por lado = metade do spread típico × multiplicador + comissão
        fees = {m["symbol"]: m["spread_pct"] / 100 / 2 * mcfg.spread_cost_multiplier
                + mcfg.commission_per_side_pct / 100 for m in meta}
        benchmark = mcfg.benchmarks.get(args.group)
        if args.group in mcfg.stop_pct_range:
            low, high = mcfg.stop_pct_range[args.group]
            config = _stop_range(config, low, high)
        config = config.model_copy(update={
            "universe": config.universe.model_copy(update={"min_turnover_24h_usdt": 0.0}),  # volume de ticks
            "regime": config.regime.model_copy(update={"btc_symbol": benchmark or "__sem_referencia__"})})
    else:
        if args.market == "perp":
            db_path = resolve_path(config.markets.cripto_perp.history_db)
            config = config.model_copy(update={"costs": config.costs.model_copy(
                update={"fee_rate_per_side": config.markets.cripto_perp.fee_rate_per_side})})
        else:
            db_path = resolve_path(config.market_data.history.db_path)
        selection = db_path.with_name(f"{db_path.stem}_symbols.json")
        symbols = [s["symbol"] for s in json.loads(selection.read_text(encoding="utf-8"))["symbols"]]
        benchmark = config.regime.btc_symbol
    if args.min_stop_pct is not None or args.max_stop_pct is not None:  # a linha de comando vence o mercado
        config = _stop_range(config, args.min_stop_pct, args.max_stop_pct)
    if args.fee_rate is not None:
        config = config.model_copy(update={"costs": config.costs.model_copy(
            update={"fee_rate_per_side": args.fee_rate})})
        fees = {}
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(",")}
        symbols = [s for s in symbols if s.upper() in wanted or s == benchmark]

    t0 = time.monotonic()
    store = KlineStore(db_path)
    data = {}
    bench_d1 = klines_to_frame([])  # vazio = sem ativo de referência (força relativa neutra, sem regime)
    if benchmark and benchmark in symbols + [config.regime.btc_symbol]:
        bench = load_symbol(store, benchmark, benchmark, None, config, invert=args.short, fee_rate=fees.get(benchmark))
        if bench is None:
            print(f"Sem histórico da referência {benchmark}")
            return 1
        data[benchmark], bench_d1 = bench, bench.d1
    for sym in symbols:
        if sym in data:
            continue
        sd = load_symbol(store, sym, sym.removesuffix(config.bybit.quote), bench_d1, config, invert=args.short,
                         fee_rate=fees.get(sym))
        if sd is not None:
            data[sym] = sd
    store.close()
    if not data:
        print("Nenhum ativo com histórico suficiente")
        return 1
    starts = [int(sd.trig["start_ms"].iloc[0]) for sd in data.values()]  # o teste começa quando há gatilho
    ends = [int(sd.h1["start_ms"].iloc[-1]) for sd in data.values()]
    first = max((int(data[benchmark].h1["start_ms"].iloc[0]) if benchmark in data else min(starts))
                + config.backtest.warmup_days * 86_400_000, min(starts))
    last = max(ends) + 3_600_000
    side = "VENDAS (gráfico invertido)" if args.short else "compras"
    print(f"{args.market}{'/' + args.group if args.group else ''}: {len(data)} ativos em {time.monotonic() - t0:.0f} s;"
          f" {datetime.fromtimestamp(first / 1000, UTC):%d/%m/%Y} a {datetime.fromtimestamp(last / 1000, UTC):%d/%m/%Y}"
          f" | {side} | setups: {', '.join(config.setups.enabled)} | gatilho {config.setups.trigger_interval}"
          f" | custo/lado {('por ativo (spread)' if fees else f'{config.costs.fee_rate_per_side:.4%}')}"
          f" | stop {config.setups.common.min_stop_pct:g}–{config.setups.common.max_stop_pct:g}%")

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


def _stop_range(config, low: float | None, high: float | None):
    update = {k: v for k, v in (("min_stop_pct", low), ("max_stop_pct", high)) if v is not None}
    return config.model_copy(update={"setups": config.setups.model_copy(update={
        "common": config.setups.common.model_copy(update=update)})})


if __name__ == "__main__":
    sys.exit(main())
