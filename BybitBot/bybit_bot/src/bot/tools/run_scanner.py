"""Roda uma varredura completa e mostra o ranking (Gate 3).

    python -m bot.tools.run_scanner                      # só mostra (dados públicos, roda no PC)
    GCP_PROJECT=bybit-scanner-bot python -m bot.tools.run_scanner --send   # envia ao painel (VM)

O estado do circuit breaker fica em data/scanner_state.json e as velas em market_data.db_path
(a segunda varredura só busca as velas novas).
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
from bot.markets.stats import STATS_FILE, load_stats_file
from bot.reporting.dashboard_client import DashboardClient
from bot.scanner.regime import RegimeState
from bot.scanner.scanner import LABEL_BY_LIST, Scanner, scanner_payload
from bot.secrets import SecretProvider, load_dotenv_if_local
from bot.signals.feed import FeedState, send_events
from bot.storage.kline_store import KlineStore

STATE_PATH = "data/scanner_state.json"
FEED_STATE = "data/feed_state.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Varredura do scanner")
    parser.add_argument("--send", action="store_true", help="envia o scanner_run ao painel")
    parser.add_argument("--top", type=int, default=20, help="linhas no resumo impresso")
    args = parser.parse_args(argv)

    config = load_config()
    load_dotenv_if_local()
    setup_logging(config.logging.level)
    client = BybitClient.from_config(config, secrets=None, mode="paper")  # dados públicos
    client.sync_time()
    store = KlineStore(resolve_path(config.market_data.db_path))
    md = MarketData(client, config.market_data, store=store)
    registry = InstrumentRegistry.load(client, quote=config.bybit.quote)
    state_path = resolve_path(STATE_PATH)
    state = RegimeState.load(state_path)

    stats = load_stats_file(resolve_path(STATS_FILE)).get("cripto_spot_long")
    feed_state = FeedState.load(resolve_path(FEED_STATE))
    scan = Scanner(md, registry, config, state, analyst=gemini_analyst(config), stats=stats,
                   feed_state=feed_state).run()
    state.save(state_path)

    tz = ZoneInfo(config.timezone)
    rg = scan.regime
    print(f"\n===== SCANNER — {rg.regime.upper()} — {scan.duration_ms / 1000:.1f} s =====")
    for reason in rg.reasons:
        print(f"  · {reason}")
    print(f"Universo: {scan.universe_size} moedas | Watchlist A: {scan.candidates} | "
          f"Watchlist B: {sum(r.watchlist == 'B' for r in scan.results)} | erros: {len(scan.errors)}")
    print("Fora do universo:", dict(scan.rejected.most_common(8)))
    header = f"{'#':>3} {'par':<14}{'score':>6} {'lista':<12}{'tend':>5}{'f.rel':>6}{'vol':>5}{'comp':>5}" \
             f"{'deriv':>6}{'mom':>5}{'pen':>5}{'RSI4h':>7}  observação"
    print(header)
    for i, r in enumerate(scan.results[: args.top], 1):
        c = r.score.components
        print(f"{i:>3} {r.coin.symbol:<14}{r.score.total:>6.1f} {LABEL_BY_LIST[r.watchlist]:<12}"
              f"{c['trend']:>5g}{c['relative_strength']:>6g}{c['volume']:>5g}{c['squeeze']:>5g}"
              f"{c['derivatives']:>6g}{c['momentum']:>5g}{r.score.penalties:>5g}{r.features.rsi_4h:>7.1f}  "
              f"{r.note or ''}")
    print(f"Horário: {datetime.fromtimestamp(scan.run_at_ms / 1000, tz):%d/%m %H:%M} ({config.timezone})")
    for r in scan.results:
        if r.gemini:
            print(f"  {r.coin.symbol}: {r.gemini.line()}")

    exit_code = 0
    if args.send:
        dashboard = DashboardClient.from_config(config, SecretProvider())
        if dashboard is None:
            print("Painel desligado no config (dashboard.enabled = false).")
        else:
            payload = scanner_payload(scan, config.score, config.dashboard.max_results_per_run)
            result = dashboard.send("scanner_run", payload)
            print(f"Painel: {'OK' if result.ok else 'FALHOU'} (HTTP {result.status}) {result.body or ''}")
            exit_code = 0 if result.ok else 1
            sent, failed = send_events(scan.events, feed_state, dashboard)
            print(f"Painel (aba Sinais): {sent} eventos novos enviados, {failed} falhas")
            exit_code |= 1 if failed else 0
            dashboard.close()
    feed_state.save(resolve_path(FEED_STATE))   # situação dos planos (para detectar mudanças)
    store.close()
    client.close()
    return exit_code


def gemini_analyst(config):
    """Analista Gemini só com gemini.enabled e gemini.calls_enabled (chamadas reais geram custo)."""
    g = config.gemini
    if not (g.enabled and g.calls_enabled):
        return None
    from bot.ai.gemini_analyst import GeminiAnalyst

    return GeminiAnalyst(g, resolve_path("data/gemini"))


if __name__ == "__main__":
    sys.exit(main())
