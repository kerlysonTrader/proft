"""Scanner multi-mercado do MT5 (SOMENTE LEITURA) — roda no PC com o MT5 da corretora aberto.

    python -m bot.tools.run_mt5_scanner                      # só mostra no terminal
    python -m bot.tools.run_mt5_scanner --send               # envia ao painel (execução própria "MT5")
    python -m bot.tools.run_mt5_scanner --send --loop 15     # repete a cada 15 min (Ctrl+C para parar)

O token do painel vem do Secret Manager (projeto --project) pelo gcloud já logado no PC; nunca é
mostrado. Os alertas (setup disparou e passou nos filtros) vão para Sinais e Logs do painel, uma
única vez por vela. Nunca envia ordens: você decide e executa.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.config import load_config, resolve_path
from bot.logging_setup import setup_logging
from bot.markets.mt5_scanner import (
    LABEL_BY_LIST,
    Mt5Scan,
    Mt5Scanner,
    alert_signal_payload,
    alert_text,
    mt5_payload,
)
from bot.markets.mt5_source import Mt5Error, Mt5Reader
from bot.markets.stats import STATS_FILE, load_stats, load_stats_file
from bot.reporting.dashboard_client import DashboardClient
from bot.secrets import SecretProvider
from bot.signals.feed import FeedState, send_events
from bot.tools.run_scanner import gemini_analyst

STATE_DIR = "data/mt5_state"
SENT_PATH = "data/mt5_state/alertas_enviados.json"
FEED_STATE = "data/mt5_state/feed_state.json"
DEFAULT_PROJECT = "bybit-scanner-bot"


def backtest_stats(config, groups: list[str]) -> dict:
    """(grupo, direção) -> estatística dos trades do run_backtest (labels mt5_<grupo>_<long|short>)."""
    saved = load_stats_file(resolve_path(STATS_FILE))
    out = {}
    for group in groups:
        for direction, side in ((1, "long"), (-1, "short")):
            key = f"mt5_{group}_{side}"
            out[(group, direction)] = saved.get(key) or load_stats(resolve_path(f"data/backtest/{key}_trades.csv"))
    return out


def print_scan(scan: Mt5Scan, config, top: int) -> None:
    tz = ZoneInfo(config.timezone)
    when = datetime.fromtimestamp(scan.run_at_ms / 1000, tz)
    print(f"\n===== SCANNER MT5 — {when:%d/%m %H:%M} ({config.timezone}) — {scan.duration_ms / 1000:.1f} s =====")
    for name, regime in scan.regimes.items():
        if regime.regime != "risk_on":
            print(f"  · {name}: {regime.regime}")
    print(f"{'#':>3} {'ativo':<20}{'score':>6} {'lista':<12}{'tend':>5}{'vol':>5}{'comp':>5}{'mom':>5}{'pen':>5}"
          f"{'24h%':>7}  observação")
    for i, r in enumerate(scan.rows[:top], 1):
        c = r.score.components
        obs = "ALERTA" if r.alerts else ("barrado" if r.blocked else "")
        obs += "" if r.market_open else " (mercado fechado)"
        print(f"{i:>3} {r.label:<20}{r.score.total:>6.1f} {LABEL_BY_LIST[r.watchlist]:<12}{c['trend']:>5g}"
              f"{c['volume']:>5g}{c['squeeze']:>5g}{c['momentum']:>5g}{r.score.penalties:>5g}"
              f"{r.change_24h_pct:>7.2f}  {obs}")
    for row, signal in scan.alerts:
        print(" ", alert_text(row, signal))
    for r in scan.rows:
        if r.gemini:
            print(f"  {r.label}: {r.gemini.line()}")
    if scan.errors:
        print("Erros:", scan.errors)


def load_sent() -> list[str]:
    try:
        return list(json.loads(resolve_path(SENT_PATH).read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError):
        return []


def save_sent(sent: list[str]) -> None:
    path = resolve_path(SENT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sent[-500:]), encoding="utf-8")


def send_scan(scan: Mt5Scan, config, dashboard: DashboardClient, feed_state: FeedState | None = None) -> bool:
    result = dashboard.send("scanner_run", mt5_payload(scan, config.score, config.dashboard.max_results_per_run))
    print(f"Painel (scanner MT5): {'OK' if result.ok else 'FALHOU'} (HTTP {result.status})")
    ok = result.ok
    sent = load_sent()
    for row, signal in scan.alerts:
        if signal.order_link_id in sent:
            continue
        r1 = dashboard.send("signal", alert_signal_payload(row, signal))
        r2 = dashboard.send("log", {"level": "warning", "component": "mt5_scanner", "symbol": row.label,
                                    "message": alert_text(row, signal),
                                    "data": {"setup": signal.setup, "entry": signal.entry, "stop": signal.stop,
                                             "tp1": signal.tp1, "tp2": signal.tp2, "grupo": row.group}})
        print(f"Painel (alerta {signal.order_link_id}): sinal {r1.status}, log {r2.status}")
        if r1.ok and r2.ok:
            sent.append(signal.order_link_id)
        ok &= r1.ok and r2.ok
    save_sent(sent)
    if feed_state is not None:
        n_ok, n_fail = send_events(scan.events, feed_state, dashboard)
        print(f"Painel (aba Sinais): {n_ok} eventos novos enviados, {n_fail} falhas")
        ok = ok and not n_fail
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scanner do MT5 (somente leitura)")
    parser.add_argument("--send", action="store_true", help="envia ao painel")
    parser.add_argument("--loop", type=float, default=0, help="repete a cada N minutos (0 = uma vez)")
    parser.add_argument("--groups", default=None, help="grupos separados por vírgula (padrão: todos)")
    parser.add_argument("--top", type=int, default=25, help="linhas no resumo impresso")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="projeto do Secret Manager (token do painel)")
    args = parser.parse_args(argv)

    config = load_config()
    setup_logging("WARNING")
    mcfg = config.markets.mt5
    groups = [g.strip() for g in args.groups.split(",")] if args.groups else list(mcfg.groups)
    unknown = [g for g in groups if g not in mcfg.groups]
    if unknown:
        print(f"Grupos desconhecidos: {unknown}; existentes: {', '.join(mcfg.groups)}")
        return 1
    dashboard = None
    if args.send:
        dashboard = DashboardClient.from_config(config, SecretProvider(project=args.project))
        if dashboard is None:
            print("Painel desligado no config (dashboard.enabled = false).")
            return 1

    exit_code = 0
    analyst = gemini_analyst(config)
    print("Gemini:", f"ligado ({config.gemini.model_screening})" if analyst else "desligado (sem custo)")
    reader = Mt5Reader(mcfg.server_utc_offset_hours, mcfg.max_bars)
    connected = False
    try:
        while True:
            try:
                if not connected:
                    reader.__enter__()
                    connected = True
                    info = reader.describe()
                    print(f"MT5: {info['server']} | conectado={info['connected']} | somente leitura")
                exit_code = run_once(reader, config, groups, analyst, dashboard, args.top)
                if exit_code == 2:   # sem dados: MT5 fechado/desconectado -> reconecta no próximo ciclo
                    reader.__exit__(None, None, None)
                    connected = False
            except Mt5Error as exc:
                print(f"MT5: {exc} — tento de novo no próximo ciclo (o MT5 está aberto e logado?)")
                exit_code, connected = 1, False
            except Exception as exc:  # um ciclo com erro não derruba o laço
                print(f"Erro no ciclo: {type(exc).__name__}: {exc}")
                exit_code = 1
            if args.loop <= 0:
                break
            time.sleep(_seconds_to_next(args.loop))
    except KeyboardInterrupt:
        print("\nParado pelo usuário.")
    finally:
        if connected:
            reader.__exit__(None, None, None)
        if dashboard is not None:
            dashboard.close()
    return exit_code


def run_once(reader: Mt5Reader, config, groups: list[str], analyst, dashboard, top: int) -> int:
    """Uma varredura. 0 = ok, 1 = falha ao enviar, 2 = sem dados do MT5 (nada é enviado)."""
    mcfg = config.markets.mt5
    reader.detect_offset([s for g in groups for s in mcfg.groups[g]])
    feed_state = FeedState.load(resolve_path(FEED_STATE))
    scan = Mt5Scanner(reader, config, groups, backtest_stats(config, groups),
                      state_dir=resolve_path(STATE_DIR), analyst=analyst, feed_state=feed_state).run()
    if not scan.rows:
        print(f"MT5 sem dados ({len(scan.errors)} erros de leitura) — nada enviado ao painel")
        return 2
    print_scan(scan, config, top)
    if not any(r.market_open for r in scan.rows):
        print("Mercados fechados (sem velas novas) — nada enviado ao painel")
        return 0
    code = 0
    if dashboard is not None:
        code = 0 if send_scan(scan, config, dashboard, feed_state) else 1
    feed_state.save(resolve_path(FEED_STATE))   # situação dos planos e eventos já enviados
    return code


def _seconds_to_next(minutes: float) -> float:
    """Até o próximo múltiplo de N minutos + 20 s (a vela de 15m já fechou no servidor)."""
    step = minutes * 60
    return step - (time.time() % step) + 20


if __name__ == "__main__":
    sys.exit(main())
