from __future__ import annotations

from decimal import Decimal

import pytest

from bot.bybit.instruments import (
    InstrumentRegistry,
    InstrumentRules,
    OrderValidationError,
    UnknownSymbolError,
    fmt,
    quantize_step,
)

BTC = {
    "symbol": "BTCUSDT",
    "baseCoin": "BTC",
    "quoteCoin": "USDT",
    "status": "Trading",
    "lotSizeFilter": {
        "basePrecision": "0.000001",
        "quotePrecision": "0.00000001",
        "minOrderQty": "0.000048",
        "maxOrderQty": "71.73956243",
        "minOrderAmt": "1",
        "maxOrderAmt": "2000000",
    },
    "priceFilter": {"tickSize": "0.01"},
}


@pytest.fixture
def btc() -> InstrumentRules:
    return InstrumentRules.from_api(BTC)


def test_quantidade_sempre_para_baixo(btc):
    assert btc.round_qty("0.0012349") == Decimal("0.001234")
    assert btc.round_qty(Decimal("0.0000019")) == Decimal("0.000001")
    assert btc.round_qty("1") == Decimal("1.000000")


@pytest.mark.parametrize(
    "price, rounding, expected",
    [("50000.006", "nearest", "50000.01"), ("50000.006", "down", "50000.00"),
     ("50000.001", "up", "50000.01"), ("50000.005", "nearest", "50000.01")],
)
def test_preco_no_tick(btc, price, rounding, expected):
    assert btc.round_price(price, rounding) == Decimal(expected)


def test_tick_nao_decimal():
    assert quantize_step(Decimal("1.37"), Decimal("0.5"), "down") == Decimal("1.0")
    assert quantize_step(Decimal("1.37"), Decimal("0.5"), "up") == Decimal("1.5")


def test_validate_order_ok(btc):
    qty, price = btc.validate_order("0.0012349", "50000.006")
    assert (qty, price) == (Decimal("0.001234"), Decimal("50000.01"))


@pytest.mark.parametrize(
    "qty, price, fragment",
    [
        ("0.00001", "50000", "abaixo do mínimo"),       # minOrderQty
        ("0.000049", "10000", "valor"),                  # 0,49 USDT < minOrderAmt
        ("80", "50000", "acima do máximo"),              # maxOrderQty
        ("0.0000001", "50000", "abaixo do mínimo"),      # arredonda para zero
    ],
)
def test_validate_order_recusa(btc, qty, price, fragment):
    with pytest.raises(OrderValidationError, match=fragment):
        btc.validate_order(qty, price)


def test_par_fora_de_negociacao():
    rules = InstrumentRules.from_api({**BTC, "status": "PreLaunch"})
    with pytest.raises(OrderValidationError, match="não está em negociação"):
        rules.validate_order("0.001", "50000")


def test_menor_quantidade_valida(btc):
    qty = btc.min_qty_for_price("50000")
    assert qty == Decimal("0.000048")  # minOrderQty domina (1 USDT / 50000 = 0,00002)
    cheap = InstrumentRules.from_api({**BTC, "lotSizeFilter": {**BTC["lotSizeFilter"], "minOrderAmt": "5"}})
    qty = cheap.min_qty_for_price("50000")
    assert qty == Decimal("0.000100")
    cheap.validate_order(qty, "50000")


def test_fmt_sem_notacao_cientifica():
    assert fmt(Decimal("0.000100")) == "0.0001"
    assert fmt(Decimal("1E-7")) == "0.0000001"
    assert fmt(Decimal("50000.00")) == "50000"
    assert fmt(Decimal("0")) == "0"


class FakeSource:
    def __init__(self, items):
        self.items = items

    def get_instruments_info(self, symbol=None, category="spot"):
        assert category == "spot"
        return self.items


def test_registry_filtra_quote_e_ignora_itens_ruins():
    items = [BTC, {**BTC, "symbol": "BTCUSDC", "quoteCoin": "USDC"}, {"symbol": "RUIM", "quoteCoin": "USDT"}]
    registry = InstrumentRegistry.load(FakeSource(items), quote="USDT")
    assert registry.symbols() == ["BTCUSDT"]
    assert "BTCUSDT" in registry
    assert registry.round_qty("BTCUSDT", "0.0012349") == Decimal("0.001234")
    with pytest.raises(UnknownSymbolError):
        registry.get("ETHUSDT")


def test_registry_carrega_pelo_cliente_com_paginacao(fake, make_client):
    from conftest import ok

    eth = {**BTC, "symbol": "ETHUSDT", "baseCoin": "ETH"}
    fake.on("GET", "/v5/market/instruments-info",
            ok({"list": [BTC], "nextPageCursor": "p2"}), ok({"list": [eth], "nextPageCursor": ""}))
    registry = InstrumentRegistry.load(make_client())
    assert registry.symbols() == ["BTCUSDT", "ETHUSDT"]
