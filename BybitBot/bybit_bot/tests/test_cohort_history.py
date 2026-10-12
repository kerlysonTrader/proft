from __future__ import annotations

import httpx
import pytest

from bot.bybit.instruments import InstrumentRegistry, InstrumentRules
from bot.config import load_config
from bot.onchain.cohort_history import (
    CohortHistoryStore,
    CoinPair,
    CoinversaClient,
    CoinversaError,
    export_history,
    hl_coin_for,
    is_crypto_hl_coin,
    select_pairs,
)
from conftest import CONFIG_PATH


@pytest.fixture
def config():
    return load_config(CONFIG_PATH)


def rules(symbol, base):
    return InstrumentRules.from_api({
        "symbol": symbol, "baseCoin": base, "quoteCoin": "USDT", "status": "Trading",
        "lotSizeFilter": {"basePrecision": "0.01", "minOrderQty": "0.01", "minOrderAmt": "1"},
        "priceFilter": {"tickSize": "0.0000001"},
    })


def test_mapeamento_nativo_override_e_negado(config):
    sm = config.onchain.symbol_map
    assert hl_coin_for("btc", sm) == ("BTC", 1)
    assert hl_coin_for("PEPE", sm) == ("kPEPE", 1000)
    denied = sm.model_copy(update={"deny": ["SOL"]})
    assert hl_coin_for("SOL", denied) is None


def test_filtra_coins_que_nao_sao_cripto(config):
    patterns = config.onchain.symbol_map.exclude_hl_patterns
    assert is_crypto_hl_coin("ETH", patterns)
    assert not is_crypto_hl_coin("xyz:TSLA", patterns)
    assert not is_crypto_hl_coin("#123", patterns)
    assert not is_crypto_hl_coin("@107", patterns)


def test_selecao_de_pares(config):
    registry = InstrumentRegistry({r.symbol: r for r in [
        rules("BTCUSDT", "BTC"), rules("ETHUSDT", "ETH"), rules("PEPEUSDT", "PEPE"), rules("USDCUSDT", "USDC"),
        rules("ABCUSDT", "ABC"), rules("LOWUSDT", "LOW"), rules("NOHLUSDT", "NOHL"),
    ]})
    big = "10000000"
    tickers = {
        "BTCUSDT": {"lastPrice": "100000", "turnover24h": "1"},          # BTC entra mesmo com volume baixo
        "ETHUSDT": {"lastPrice": "2500", "turnover24h": big},
        "PEPEUSDT": {"lastPrice": "0.00001", "turnover24h": big},       # HL kPEPE = 0.01 -> /1000 ok
        "USDCUSDT": {"lastPrice": "1", "turnover24h": big},             # stablecoin excluída
        "ABCUSDT": {"lastPrice": "10", "turnover24h": big},             # colisão de ticker: preço HL 50
        "LOWUSDT": {"lastPrice": "1", "turnover24h": "1000"},           # volume baixo
        "NOHLUSDT": {"lastPrice": "1", "turnover24h": big},             # sem perp na HL
    }
    hl = [
        {"coin": "BTC", "dex": "hl", "markPx": 100100}, {"coin": "ETH", "dex": "hl", "markPx": 2501},
        {"coin": "kPEPE", "dex": "hl", "markPx": 0.01}, {"coin": "USDC", "dex": "hl", "markPx": 1},
        {"coin": "ABC", "dex": "hl", "markPx": 50}, {"coin": "LOW", "dex": "hl", "markPx": 1},
        {"coin": "xyz:ETH", "dex": "xyz", "markPx": 2500}, {"coin": "NOHL", "dex": "km", "markPx": 1},
    ]
    pairs = select_pairs(tickers, registry, config.universe, config.onchain.symbol_map, hl, always=("BTCUSDT",))
    assert pairs == [CoinPair("BTCUSDT", "BTC", 1), CoinPair("ETHUSDT", "ETH", 1),
                     CoinPair("PEPEUSDT", "kPEPE", 1000)]


ROW = {"timestamp": 1791162000000, "coin": "BTC", "tierType": "pnl", "tier": "smart_money",
       "longNotional": 10.0, "shortNotional": 5.0, "netBias": 33.3, "accountCount": 120}


def test_store_upsert_idempotente_e_cobertura():
    store = CohortHistoryStore(":memory:")
    rows = [ROW, {**ROW, "tier": "exit_liquidity"}, {**ROW, "timestamp": ROW["timestamp"] + 3_600_000}]
    assert store.upsert(rows, 1) == 3
    store.upsert(rows, 2)  # repetir não duplica
    assert store.coverage() == [("BTC", ROW["timestamp"], ROW["timestamp"] + 3_600_000, 2)]
    assert store.upsert([{"coin": "BTC"}], 3) == 0  # linha incompleta ignorada


class FakeCoinversa:
    def __init__(self, fail=()):
        self.fail = set(fail)
        self.calls = []

    def cohort_history(self, coin, since):
        self.calls.append((coin, since))
        if coin in self.fail:
            raise CoinversaError("HTTP 500")
        return [{**ROW, "coin": coin}]


def test_export_continua_depois_de_falha():
    store = CohortHistoryStore(":memory:")
    fake = FakeCoinversa(fail={"ETH"})
    pairs = [CoinPair("BTCUSDT", "BTC", 1), CoinPair("ETHUSDT", "ETH", 1), CoinPair("SOLUSDT", "SOL", 1)]
    result = export_history(fake, store, pairs, "90d", now_ms=lambda: 1)
    assert result == {"coins": 3, "rows": 2, "failures": ["ETH"]}
    assert fake.calls == [("BTC", "90d"), ("ETH", "90d"), ("SOL", "90d")]


def make_client(handler, sleeps):
    return CoinversaClient("https://api.example/v1", "cvsa_teste123", http_client=httpx.Client(
        transport=httpx.MockTransport(handler)), sleep=sleeps.append, min_interval_ms=0,
        monotonic=lambda: 0.0, clock=lambda: 1000.0)


def test_cliente_envia_header_e_respeita_429():
    seen, sleeps = [], []
    responses = [httpx.Response(429, json={"retryAfterSeconds": 7}), httpx.Response(200, json={"history": [ROW]})]

    def handler(request):
        seen.append(request)
        return responses.pop(0)

    rows = make_client(handler, sleeps).cohort_history("BTC", "90d")
    assert rows == [ROW]
    assert sleeps == [7.0]
    assert seen[-1].headers["X-API-Key"] == "cvsa_teste123"
    assert dict(seen[-1].url.params) == {"coin": "BTC", "since": "90d"}


def test_cliente_espera_reset_quando_cota_zera():
    sleeps = []
    handler = lambda r: httpx.Response(200, json=[ROW], headers={"x-ratelimit-remaining": "0",  # noqa: E731
                                                                 "x-ratelimit-reset": "1010"})
    make_client(handler, sleeps).cohort_history("BTC", "1h")
    assert sleeps == [pytest.approx(10.5)]


def test_cliente_erro_4xx_nao_repete():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, text="unauthorized")

    with pytest.raises(CoinversaError) as exc:
        make_client(handler, []).cohort_history("BTC", "1h")
    assert exc.value.status == 401 and len(calls) == 1
