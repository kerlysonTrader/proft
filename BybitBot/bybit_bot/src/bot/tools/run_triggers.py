"""Gatilhos de entrada (Gate 4).

    python -m bot.tools.run_triggers                       # varre, roda os setups na Watchlist A agora
    python -m bot.tools.run_triggers --replay 168          # sinais que teriam disparado nas últimas 168 h
    GCP_PROJECT=bybit-scanner-bot python -m bot.tools.run_triggers --send   # envia os aprovados ao painel

O replay usa o score da varredura atual (aproximação) e as velas de cada hora passada, só para
conferir visualmente no gráfico se entrada/stop/alvos fazem sentido. O backtest de verdade é a Fase 5.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.bybit.client import BybitClient
from bot.bybit.instruments import InstrumentRegistry
from bot.config import load_config, resolve_path
from bot.data.market_data import MarketData
from bot.logging_setup import setup_logging
from bot.reporting.dashboard_client import DashboardClient
from bot.scanner.regime import RegimeState
from bot.scanner.scanner import Scanner
from bot.secrets import SecretProvider, load_dotenv_if_local
from bot.signals.engine import evaluate, signal_payload
from bot.signals.filters import SignalContext
from bot.storage.kline_store import KlineStore

H = 3_600_000
LABEL = {"pullback_tendencia": "Pullback", "rompimento_compressao": "Rompimento", "ote_fibo": "OTE Fibo"}


def fmt_price(value: float) -> str:
    return f"{value:.6g}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gatilhos de entrada da Watchlist A")
    parser.add_argument("--send", action="store_true", help="envia os sinais aprovados ao painel")
    parser.add_argument("--replay", type=int, default=0, help="horas passadas a simular (0 = só agora)")
    parser.add_argument("--include-b", action="store_true", help="inclui a Watchlist B (útil no replay)")
    args = parser.parse_args(argv)

    config = load_config()
    load_dotenv_if_local()
    setup_logging("WARNING")
    tz = ZoneInfo(config.timezone)
    client = BybitClient.from_config(config, secrets=None, mode="paper")
    client.sync_time()
    store = KlineStore(resolve_path(config.market_data.db_path))
    md = MarketData(client, config.market_data, store=store)
    registry = InstrumentRegistry.load(client, quote=config.bybit.quote)
    state_path = resolve_path("data/scanner_state.json")
    state = RegimeState.load(state_path)
    scan = Scanner(md, registry, config, state).run()
    state.save(state_path)

    lists = ("A", "B") if args.include_b else ("A",)
    candidates = [r for r in scan.results if r.watchlist in lists]
    spreads = {r.coin.symbol: r.coin.spread_pct for r in scan.results}
    now = client.now_ms()
    print(f"\nRegime {scan.regime.regime} | novas entradas permitidas: {scan.regime.allow_new_entries} | "
          f"candidatas: {', '.join(r.coin.symbol for r in candidates) or 'nenhuma'}")

    approved, seen = [], set()
    last_closed = md.last_closed_start("60", now) + H  # fim da última vela 1H fechada
    moments = [last_closed - k * H for k in range(args.replay, -1, -1)]
    for r in candidates:
        h1 = md.klines(r.coin.symbol, "60", limit=min(1000, 300 + args.replay))
        h4 = md.klines(r.coin.symbol, "240", limit=config.score.candles.h4)
        for moment in moments:
            ctx = SignalContext(now_ms=moment, allow_new_entries=scan.regime.allow_new_entries,
                                regime=scan.regime.regime, spread_pct=spreads)
            for ev in evaluate(r.coin.symbol, h1, h4, r.score.components, r.score.total, ctx, config):
                s = ev.signal
                if s.order_link_id in seen:
                    continue
                seen.add(s.order_link_id)
                when = datetime.fromtimestamp(s.candle_start_ms / 1000, tz)
                status = "APROVADO" if ev.approved else "barrado: " + "; ".join(ev.problems)
                print(f"\n{when:%d/%m %H:%M} {s.symbol} {LABEL[s.setup]} — {status}")
                print(f"   entrada {fmt_price(s.entry)} | stop {fmt_price(s.stop)} ({s.stop_pct:.2f}%) | "
                      f"TP1 {fmt_price(s.tp1)} | TP2 {fmt_price(s.tp2)} | R:R {s.rr:.2f} | "
                      f"válida por {s.valid_candles} velas 1H")
                for reason in s.reasons:
                    print(f"   · {reason}")
                if ev.approved and moment == moments[-1]:
                    approved.append(s)
    if not seen:
        print("\nNenhum setup disparou" + (f" nas últimas {args.replay} h." if args.replay else " agora."))

    exit_code = 0
    if args.send and approved:
        dashboard = DashboardClient.from_config(config, SecretProvider())
        if dashboard:
            for s in approved:
                result = dashboard.send("signal", signal_payload(s))
                print(f"Painel: {s.order_link_id} -> {'OK' if result.ok else 'FALHOU'} (HTTP {result.status})")
                exit_code |= 0 if result.ok else 1
            dashboard.close()
    elif args.send:
        print("Nenhum sinal aprovado agora para enviar ao painel.")
    store.close()
    client.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
