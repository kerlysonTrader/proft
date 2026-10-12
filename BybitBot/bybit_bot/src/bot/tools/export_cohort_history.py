"""Copia o histórico de coortes da Coinversa para SQLite local (onchain.snapshot_log.local_db_path).

    GCP_PROJECT=bybit-scanner-bot python -m bot.tools.export_cohort_history            # 90 dias
    GCP_PROJECT=bybit-scanner-bot python -m bot.tools.export_cohort_history --refresh  # atualização diária (cron)

Moedas: pares spot/USDT da Bybit elegíveis (exclusões e volume mínimo do universo) que têm
perpétuo nativo na Hyperliquid com preço compatível. Só leitura; a chave vem do Secret Manager.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from bot.bybit.client import BybitClient
from bot.bybit.instruments import InstrumentRegistry
from bot.config import load_config, resolve_path
from bot.data.market_data import MarketData
from bot.logging_setup import get_logger, setup_logging
from bot.onchain.cohort_history import CohortHistoryStore, CoinversaClient, export_history, select_pairs
from bot.secrets import SecretProvider, load_dotenv_if_local

log = get_logger("tools.export_cohort_history")


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    oc = config.onchain
    snap = oc.snapshot_log
    parser = argparse.ArgumentParser(description="Exporta o histórico de coortes da Coinversa")
    parser.add_argument("--refresh", action="store_true",
                        help=f"janela curta ({snap.refresh_since}) para o cron diário")
    parser.add_argument("--since", default=None, help=f"janela relativa (padrão {snap.export_since})")
    parser.add_argument("--quiet", action="store_true", help="sem tabela final (para o cron)")
    args = parser.parse_args(argv)
    since = args.since or (snap.refresh_since if args.refresh else snap.export_since)

    load_dotenv_if_local()
    setup_logging(config.logging.level)
    secrets = SecretProvider()
    coinversa = CoinversaClient(oc.base_url, secrets.get(oc.api_key_secret), oc.auth_header,
                                timeout_seconds=snap.export_timeout_seconds,
                                min_interval_ms=snap.export_min_interval_ms)
    bybit = BybitClient.from_config(config, secrets=None, mode="paper")  # só dados públicos
    md = MarketData(bybit, config.market_data)
    registry = InstrumentRegistry.load(bybit, quote=config.bybit.quote)
    pairs = select_pairs(md.spot_tickers(), registry, config.universe, oc.symbol_map,
                         coinversa.market_overview(), always=(config.regime.btc_symbol,))
    store = CohortHistoryStore(resolve_path(snap.local_db_path))
    log.info("exportação iniciada", extra={"data": {"since": since, "moedas": len(pairs)}})
    result = export_history(coinversa, store, pairs, since)
    log.info("exportação concluída", extra={"data": result})

    if not args.quiet:
        print(f"\n===== HISTÓRICO DE COORTES ({since}) =====")
        failures = result["failures"] or "nenhuma"
        print(f"moedas: {result['coins']} | linhas gravadas: {result['rows']} | falhas: {failures}")
        print(f"{'coin':<10}{'de':>18}{'até':>18}{'horas':>8}")
        for coin, first, last, hours in store.coverage():
            fmt = "%Y-%m-%d %H:%M"
            print(f"{coin:<10}{datetime.fromtimestamp(first / 1000, UTC):{fmt}}  "
                  f"{datetime.fromtimestamp(last / 1000, UTC):{fmt}}{hours:>8}")
    store.close()
    coinversa.close()
    bybit.close()
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
