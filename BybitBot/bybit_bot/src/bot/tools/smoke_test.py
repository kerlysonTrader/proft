"""Smoke test da Fase 1 — SEMPRE na conta demo da Bybit (dinheiro virtual).

    python -m bot.tools.smoke_test [--config config/config.yaml] [--symbol BTCUSDT]

Passos: sincroniza o relógio, confere as permissões da chave, lê o saldo,
carrega as regras do par, baixa 200 velas 1H, cria uma ordem limite de compra
20 % abaixo do preço (valor mínimo), testa o orderLinkId repetido, confirma que a
ordem existe, cancela e confirma o cancelamento. A ordem é cancelada mesmo se
um passo intermediário falhar.

Precisa rodar de um IP liberado na chave (a VM: 34.151.204.72).
"""

from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal
from typing import Any

from bot.bybit.client import BybitClient
from bot.bybit.errors import BybitDuplicateOrderError, BybitError
from bot.bybit.instruments import InstrumentRegistry, fmt
from bot.config import load_config
from bot.logging_setup import get_logger, setup_logging
from bot.secrets import SecretProvider, load_dotenv_if_local

log = get_logger("tools.smoke_test")

KLINES_WANTED = 200
PRICE_FACTOR = Decimal("0.80")  # 20 % abaixo do preço atual: não executa
AMOUNT_MARGIN = Decimal("1.2")  # 20 % acima do valor mínimo da ordem


class Report:
    def __init__(self) -> None:
        self.steps: list[tuple[str, bool, str]] = []

    def ok(self, step: str, detail: str = "") -> None:
        self.steps.append((step, True, detail))
        log.info(f"OK: {step}", extra={"data": {"detalhe": detail}})

    def fail(self, step: str, detail: str) -> None:
        self.steps.append((step, False, detail))
        log.error(f"FALHOU: {step}", extra={"data": {"detalhe": detail}})

    @property
    def passed(self) -> bool:
        return bool(self.steps) and all(passed for _, passed, _ in self.steps)

    def print_summary(self) -> None:
        print("\n===== SMOKE TEST (conta DEMO) =====")
        for step, passed, detail in self.steps:
            print(f"[{'OK ' if passed else 'ERRO'}] {step}" + (f" — {detail}" if detail else ""))
        print("RESULTADO:", "APROVADO" if self.passed else "REPROVADO")


def check_key_permissions(info: dict[str, Any], report: Report) -> None:
    perms = info.get("permissions") or {}
    wallet = perms.get("Wallet") or []
    spot = perms.get("Spot") or []
    ips = info.get("ips") or []
    detail = f"readOnly={info.get('readOnly')} ips={ips} spot={spot}"
    if wallet:
        report.fail("permissões da chave", f"chave com permissão de Carteira {wallet} — retire saque/transferência")
    elif not spot:
        report.fail("permissões da chave", "chave sem permissão de Spot Trade")
    elif not ips or "*" in ips:
        report.fail("permissões da chave", "chave sem restrição de IP")
    else:
        extra = [k for k in ("ContractTrade", "Options", "Derivatives") if perms.get(k)]
        if extra:
            detail += f" (também tem {extra}: o robô recusa essas categorias no código)"
        report.ok("permissões da chave", detail)


def run(config_path: str | None, symbol: str) -> Report:
    report = Report()
    config = load_config(config_path)
    if config.mode == "live":
        report.fail("modo", "config em live: o smoke test só roda contra a conta demo")
        return report

    secrets = SecretProvider()
    client = BybitClient.from_config(config, secrets, mode="demo")
    log.info("smoke test iniciado", extra={"data": {"url": client.base_url, "segredos": secrets.source}})

    order_link_id = f"smoke-{int(time.time())}"
    created = False
    try:
        offset = client.sync_time()
        report.ok("relógio sincronizado", f"diferença {offset:+.0f} ms")

        check_key_permissions(client.get_api_key_info(), report)

        wallet = client.get_wallet_balance("UNIFIED")
        usdt = next((c for c in wallet.get("coin", []) if c.get("coin") == "USDT"), {})
        report.ok("saldo lido", f"patrimônio {wallet.get('totalEquity')} USD, USDT {usdt.get('walletBalance')}")

        registry = InstrumentRegistry.load(client, quote=config.bybit.quote)
        rules = registry.get(symbol)
        report.ok("regras do instrumento", f"{len(registry)} pares USDT; {symbol} tick={fmt(rules.tick_size)} "
                  f"passo={fmt(rules.base_precision)} mínimo={fmt(rules.min_order_amt)} USDT")

        klines = client.get_klines(symbol, "60", limit=KLINES_WANTED)
        now = client.now_ms()
        ordered = all(a.start_ms < b.start_ms for a, b in zip(klines, klines[1:], strict=False))
        closed = sum(k.is_closed(now) for k in klines)
        if len(klines) == KLINES_WANTED and ordered:
            report.ok("velas 1H", f"{len(klines)} velas em ordem, {closed} fechadas, último fechamento "
                      f"{klines[-1].close}")
        else:
            report.fail("velas 1H", f"recebidas {len(klines)}, ordem cronológica={ordered}")

        ticker = client.get_tickers(symbol)[0]
        last = Decimal(ticker["lastPrice"])
        price = rules.round_price(last * PRICE_FACTOR, "down")
        qty = rules.min_qty_for_price(price / AMOUNT_MARGIN)  # um pouco acima do mínimo
        qty, price = rules.validate_order(qty, price)
        result = client.place_order(symbol=symbol, side="Buy", order_type="Limit", qty=qty, price=price,
                                    order_link_id=order_link_id, time_in_force="GTC")
        created = True
        report.ok("ordem limite criada", f"compra {fmt(qty)} a {fmt(price)} (preço atual {fmt(last)}), "
                  f"orderLinkId={order_link_id}, orderId={result.get('orderId')}")

        # orderLinkId repetido: a Bybit deve recusar e o cliente devolve a ordem existente
        try:
            client._request("POST", "/v5/order/create", signed=True, retry="order_create", body={
                "category": "spot", "symbol": symbol, "side": "Buy", "orderType": "Limit",
                "qty": fmt(qty), "price": fmt(price), "timeInForce": "GTC", "orderLinkId": order_link_id})
            report.fail("orderLinkId repetido", "a Bybit aceitou uma segunda ordem com o mesmo orderLinkId")
        except BybitDuplicateOrderError as exc:
            report.ok("orderLinkId repetido", f"recusado com retCode {exc.ret_code} (mapeado como duplicado)")
        except BybitError as exc:
            report.fail("orderLinkId repetido", f"recusado com retCode {exc.ret_code} ({exc.ret_msg}) — "
                        "código não mapeado como duplicado; ajustar DUPLICATE_ORDER_CODES")
        again = client.place_order(symbol=symbol, side="Buy", order_type="Limit", qty=qty, price=price,
                                   order_link_id=order_link_id, time_in_force="GTC")
        if again.get("orderId") == result.get("orderId"):
            report.ok("place_order idempotente", "segunda chamada devolveu a mesma ordem")
        else:
            report.fail("place_order idempotente", f"orderId diferente: {again.get('orderId')}")

        found = client.get_open_orders(symbol=symbol, order_link_id=order_link_id)
        if found and found[0].get("orderStatus") in ("New", "PartiallyFilled", "Untriggered"):
            report.ok("ordem consultada", f"status {found[0].get('orderStatus')}")
        else:
            report.fail("ordem consultada", f"não encontrada nas abertas: {found}")
    except Exception as exc:  # o resumo mostra o erro; a ordem ainda é cancelada abaixo
        report.fail("execução", f"{type(exc).__name__}: {exc}")
    finally:
        if created:
            try:
                client.cancel_order(symbol=symbol, order_link_id=order_link_id)
                still_open = client.get_open_orders(symbol=symbol, order_link_id=order_link_id)
                status = (client.find_order(symbol, order_link_id) or {}).get("orderStatus")
                if still_open:
                    report.fail("ordem cancelada", f"ainda aberta: {still_open[0].get('orderStatus')}")
                elif status != "Cancelled":
                    report.fail("ordem cancelada", f"status inesperado depois do cancelamento: {status}")
                else:
                    report.ok("ordem cancelada", "status Cancelled e fora das abertas")
            except Exception as exc:
                report.fail("ordem cancelada", f"{type(exc).__name__}: {exc} — CANCELE MANUALMENTE {order_link_id}")
        try:
            executions = client.get_executions(symbol=symbol, limit=5, max_pages=1)
            report.ok("execuções consultadas", f"{len(executions)} execuções recentes em {symbol}")
        except Exception as exc:
            report.fail("execuções consultadas", f"{type(exc).__name__}: {exc}")
        client.close()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test da Fase 1 na conta demo da Bybit")
    parser.add_argument("--config", default=None, help="caminho do config.yaml")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args(argv)
    load_dotenv_if_local()
    setup_logging("INFO")
    report = run(args.config, args.symbol)
    report.print_summary()
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
