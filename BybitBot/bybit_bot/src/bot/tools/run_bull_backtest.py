"""Backtest do setup experimental bull_canal (Bull H1M1 em 15m, só compras).

    python -m bot.tools.run_bull_backtest --label bull_universo_regime
    python -m bot.tools.run_bull_backtest --no-universe --no-regime --label bull_puro
    python -m bot.tools.run_bull_backtest --min-channel-pct 0.5 --label bull_canal05

Precisa das velas de 15m no histórico (python -m bot.backtest.data_loader --months 25 --intervals 15).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime

from bot.backtest.bull_backtest import BullBacktester, BullParams, hour_context
from bot.backtest.engine import load_symbol
from bot.backtest.report import Metrics, gate_checks, render_markdown, trades_frame
from bot.backtest.walk_forward import walk_forward_windows
from bot.config import PROJECT_ROOT, load_config, resolve_path
from bot.data.market_data import klines_to_frame
from bot.logging_setup import setup_logging
from bot.signals.direction import invert_frame
from bot.storage.kline_store import KlineStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest do Bull H1M1 (15m, só compras)")
    parser.add_argument("--label", default="bull")
    parser.add_argument("--no-universe", action="store_true", help="opera todas as moedas baixadas")
    parser.add_argument("--no-regime", action="store_true", help="ignora o regime do BTC")
    parser.add_argument("--no-kill-switch", action="store_true", help="PESQUISA: desliga o kill switch")
    parser.add_argument("--min-channel-pct", type=float, default=0.24)
    parser.add_argument("--n-candles", type=int, default=4)
    parser.add_argument("--market", choices=["spot", "perp", "mt5"], default="spot")
    parser.add_argument("--group", default=None, help="grupo do MT5 (metais, forex, indices, energia)")
    parser.add_argument("--short", action="store_true", help="estuda as VENDAS (gráfico invertido)")
    args = parser.parse_args(argv)

    config = load_config()
    if args.no_kill_switch:
        config = config.model_copy(update={"risk": config.risk.model_copy(update={"max_drawdown_from_peak_pct": 100})})
    setup_logging("WARNING")
    params = BullParams(n_candles=args.n_candles, min_channel_pct=args.min_channel_pct,
                        use_universe=not args.no_universe, use_regime=not args.no_regime)

    t0 = time.monotonic()
    fees: dict[str, float] = {}
    if args.market == "mt5":
        mcfg = config.markets.mt5
        if args.group and args.group not in mcfg.groups:
            print(f"Informe --group entre: {', '.join(mcfg.groups)}")
            return 1
        db_path = resolve_path(mcfg.history_db)
        meta = [m for m in json.loads(db_path.with_name(f"{db_path.stem}_symbols.json").read_text(
            encoding="utf-8"))["symbols"] if not args.group or m["group"] == args.group]
        symbols = [m["symbol"] for m in meta]
        fees = {m["symbol"]: m["spread_pct"] / 100 / 2 * mcfg.spread_cost_multiplier
                + mcfg.commission_per_side_pct / 100 for m in meta}
        params.use_universe = params.use_regime = False  # sem universo/regime de cripto no MT5
    else:
        if args.market == "perp":
            db_path = resolve_path(config.markets.cripto_perp.history_db)
            config = config.model_copy(update={"costs": config.costs.model_copy(
                update={"fee_rate_per_side": config.markets.cripto_perp.fee_rate_per_side})})
        else:
            db_path = resolve_path(config.market_data.history.db_path)
        symbols = [s["symbol"] for s in json.loads(db_path.with_name(f"{db_path.stem}_symbols.json").read_text(
            encoding="utf-8"))["symbols"]]
    store = KlineStore(db_path)
    data15 = {}
    for sym in symbols:
        df = klines_to_frame(store.load(sym, "15"))
        df = invert_frame(df) if args.short else df
        if len(df) > 500:
            data15[sym] = df
    btc = config.regime.btc_symbol
    ctx_needed = params.use_universe or params.use_regime
    btc1h = load_symbol(store, btc, "BTC", None, config, invert=args.short) if ctx_needed else None
    data1h = {btc: btc1h} if btc1h else {}
    if ctx_needed:
        for sym in data15:
            if sym != btc:
                sd = load_symbol(store, sym, sym.removesuffix(config.bybit.quote), btc1h.d1, config,
                                 invert=args.short)
                if sd:
                    data1h[sym] = sd
    store.close()
    if not data15:
        print("Nenhum ativo com histórico de 15m suficiente")
        return 1
    origin = int(btc1h.h1["start_ms"].iloc[0]) if btc1h else min(int(df["start_ms"].iloc[0]) for df in data15.values())
    first = max(origin + config.backtest.warmup_days * 86_400_000,
                min(int(df["start_ms"].iloc[0]) for df in data15.values()))
    last = max(int(df["start_ms"].iloc[-1]) for df in data15.values())
    print(f"{len(data15)} moedas com 15m; {datetime.fromtimestamp(first / 1000, UTC):%d/%m/%Y} a "
          f"{datetime.fromtimestamp(last / 1000, UTC):%d/%m/%Y}; carregado em {time.monotonic() - t0:.0f} s",
          flush=True)

    ctx = hour_context(config, data1h, first, last) if (params.use_universe or params.use_regime) else None
    print(f"contexto por hora pronto em {time.monotonic() - t0:.0f} s", flush=True)
    result = BullBacktester(config, data15, first, last, params, ctx, fees).run()
    if args.short:
        result.notes.append("VENDAS estudadas no gráfico invertido (1/preço): o R é medido nessa escala")
    windows = walk_forward_windows(result, config.backtest.walk_forward)
    report = render_markdown(result, config, windows, title=f"Backtest Bull 15m — {args.label}")
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    report_path = PROJECT_ROOT / "reports" / f"{stamp}_{args.label}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    out_dir = resolve_path("data/backtest")
    out_dir.mkdir(parents=True, exist_ok=True)
    trades_frame(result.trades).to_csv(out_dir / f"{args.label}_trades.csv", index=False)

    m = Metrics.of(result.trades)
    checks = gate_checks(result, config.backtest.gate, windows)
    print(f"\nTrades {m.trades} | acerto {m.win_rate:.1f}% | expectância {m.expectancy_r:.3f} R | "
          f"PF {m.profit_factor:.2f} | resultado {m.pnl:.2f} USDT | taxas {m.fees:.2f} | "
          f"tempo médio {m.avg_hours:.1f} h | {time.monotonic() - t0:.0f} s")
    for c in checks:
        print(f"  [{'OK' if c.passed else 'X '}] {c.name}: {c.value}")
    print(f"Gate 5: {'APROVADO' if all(c.passed for c in checks) else 'REPROVADO'} — {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
