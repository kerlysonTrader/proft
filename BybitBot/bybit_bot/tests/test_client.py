from __future__ import annotations

import httpx
import pytest

from bot.bybit.client import BybitClient, RateLimiter
from bot.bybit.errors import (
    BybitAuthError,
    BybitDuplicateOrderError,
    BybitHTTPError,
    BybitInsufficientBalanceError,
    BybitIPNotAllowedError,
    BybitNetworkError,
    BybitOrderError,
    BybitOrderNotFoundError,
    BybitParamError,
    BybitPermissionError,
    BybitRateLimitError,
    CategoryNotAllowedError,
    EndpointNotAllowedError,
    error_from_response,
)
from conftest import SERVER_TIME_MS, err, ok, params_of


# ---------------------------------------------------------------- travas de segurança
@pytest.mark.parametrize("category", ["linear", "inverse", "option"])
def test_ordens_recusam_categoria_que_nao_e_spot_antes_de_chamar_a_bybit(fake, make_client, category):
    client = make_client()
    with pytest.raises(CategoryNotAllowedError):
        client.place_order(symbol="BTCUSDT", side="Buy", order_type="Limit", qty="1", price="1",
                           order_link_id="x", category=category)
    with pytest.raises(CategoryNotAllowedError):
        client.cancel_order(symbol="BTCUSDT", order_link_id="x", category=category)
    with pytest.raises(CategoryNotAllowedError):
        client.get_open_orders(category=category)
    assert fake.requests == []


@pytest.mark.parametrize("category", ["inverse", "option"])
def test_dados_publicos_recusam_inverse_e_option(fake, make_client, category):
    with pytest.raises(CategoryNotAllowedError):
        make_client().get_klines("BTCUSDT", "60", category=category)
    assert fake.requests == []


def test_dados_publicos_de_perpetuo_linear_sao_permitidos(fake, make_client):
    fake.on("GET", "/v5/market/open-interest", ok({"list": [{"openInterest": "100", "timestamp": "1"}]}))
    fake.on("GET", "/v5/market/account-ratio", ok({"list": [{"buyRatio": "0.6", "sellRatio": "0.4"}]}))
    client = make_client()
    assert client.get_open_interest("BTCUSDT")[0]["openInterest"] == "100"
    assert client.get_account_ratio("BTCUSDT")[0]["buyRatio"] == "0.6"
    oi_request = fake.calls("GET", "/v5/market/open-interest")[0]
    assert params_of(oi_request) == {"category": "linear", "symbol": "BTCUSDT", "intervalTime": "1h",
                                     "limit": "25"}
    assert "X-BAPI-SIGN" not in oi_request.headers


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/v5/asset/withdraw/create"),
        ("POST", "/v5/asset/transfer/inter-transfer"),
        ("POST", "/v5/position/set-leverage"),
        ("GET", "/v5/position/list"),
    ],
)
def test_recusa_endpoint_privado_fora_da_lista(fake, make_client, method, path):
    with pytest.raises(EndpointNotAllowedError):
        make_client()._request(method, path, signed=True)
    assert fake.requests == []


def test_chamada_privada_sem_chave_falha(fake, make_client):
    client = make_client(api_key=None, api_secret=None)
    with pytest.raises(Exception, match="sem chave"):
        client.get_wallet_balance()


# ---------------------------------------------------------------- mapeamento de erros
@pytest.mark.parametrize(
    "code, exc_type",
    [
        (10010, BybitIPNotAllowedError),
        (10005, BybitPermissionError),
        (10003, BybitAuthError),
        (10004, BybitAuthError),
        (33004, BybitAuthError),
        (10006, BybitRateLimitError),
        (10001, BybitParamError),
        (110001, BybitOrderNotFoundError),
        (170213, BybitOrderNotFoundError),
        (110072, BybitDuplicateOrderError),
        (170131, BybitInsufficientBalanceError),
        (170136, BybitOrderError),
    ],
)
def test_error_from_response(code, exc_type):
    exc = error_from_response(code, "msg", "/v5/x")
    assert isinstance(exc, exc_type)
    assert exc.ret_code == code


def test_ip_nao_liberado_nao_tenta_de_novo(fake, make_client, clock):
    fake.on("GET", "/v5/account/wallet-balance", err(10010, "Unmatched IP"))
    with pytest.raises(BybitIPNotAllowedError):
        make_client().get_wallet_balance()
    assert len(fake.calls("GET", "/v5/account/wallet-balance")) == 1


# ---------------------------------------------------------------- retentativas
def test_limite_10006_tenta_de_novo_com_espera(fake, make_client, clock):
    fake.on("GET", "/v5/market/tickers", err(10006, "Too many visits"), ok({"list": [{"symbol": "BTCUSDT"}]}))
    tickers = make_client().get_tickers("BTCUSDT")
    assert tickers == [{"symbol": "BTCUSDT"}]
    assert len(fake.calls("GET", "/v5/market/tickers")) == 2
    assert 0.5 in clock.sleeps  # backoff base * 2^0 com rng=1


@pytest.mark.parametrize("status", [429, 403])
def test_http_429_e_403_tentam_de_novo(fake, make_client, status):
    fake.on("GET", "/v5/market/tickers", httpx.Response(status, text="limite"), ok({"list": []}))
    assert make_client().get_tickers() == []
    assert len(fake.calls("GET", "/v5/market/tickers")) == 2


def test_desiste_depois_de_max_retries(fake, make_client, clock):
    fake.on("GET", "/v5/market/tickers", httpx.Response(429, text="limite"))
    with pytest.raises(BybitRateLimitError):
        make_client(max_retries=2).get_tickers()
    assert len(fake.calls("GET", "/v5/market/tickers")) == 3
    assert clock.sleeps == [0.5, 1.0]


def test_backoff_respeita_o_maximo(make_client):
    client = make_client(backoff_base_seconds=1, backoff_max_seconds=4)
    assert [client._backoff(i) for i in range(5)] == [1, 2, 4, 4, 4]


def test_erro_5xx_em_leitura_tenta_de_novo(fake, make_client):
    fake.on("GET", "/v5/market/tickers", httpx.Response(502, text="bad gateway"), ok({"list": []}))
    assert make_client().get_tickers() == []


def test_falha_de_rede_em_leitura_tenta_de_novo(fake, make_client):
    fake.on("GET", "/v5/market/tickers", httpx.ConnectTimeout("timeout"), ok({"list": []}))
    assert make_client().get_tickers() == []


def test_resposta_nao_json(fake, make_client):
    fake.on("GET", "/v5/market/tickers", httpx.Response(200, text="<html>erro</html>"))
    with pytest.raises(BybitHTTPError, match="não-JSON"):
        make_client().get_tickers()


def test_timestamp_recusado_ressincroniza_e_repete(fake, make_client, clock):
    fake.on("GET", "/v5/account/wallet-balance", err(10002, "invalid timestamp"), ok({"list": [{"a": 1}]}))
    client = make_client()
    assert client.get_wallet_balance() == {"a": 1}
    assert len(fake.calls("GET", "/v5/market/time")) == 2  # sync inicial + ressincronização


# ---------------------------------------------------------------- horário
def test_sincronizacao_calcula_diferenca(fake, make_client, clock):
    clock.now = SERVER_TIME_MS / 1000 - 3  # relógio local 3 s atrasado
    client = make_client()
    offset = client.sync_time()
    assert round(offset) == 3000
    assert abs(client.now_ms() - SERVER_TIME_MS) < 5


def test_ressincroniza_depois_do_intervalo(fake, make_client, clock):
    fake.on("GET", "/v5/account/wallet-balance", ok({"list": [{}]}))
    client = make_client(time_sync_minutes=30)
    client.get_wallet_balance()
    client.get_wallet_balance()
    assert len(fake.calls("GET", "/v5/market/time")) == 1
    clock.now += 31 * 60
    client.get_wallet_balance()
    assert len(fake.calls("GET", "/v5/market/time")) == 2


# ---------------------------------------------------------------- limites
def test_le_headers_de_limite(fake, make_client):
    fake.on("GET", "/v5/market/tickers", httpx.Response(200, json=ok({"list": []}), headers={
        "X-Bapi-Limit": "20", "X-Bapi-Limit-Status": "19", "X-Bapi-Limit-Reset-Timestamp": "1700000001000"}))
    client = make_client()
    client.get_tickers()
    assert (client.rate_limit.limit, client.rate_limit.remaining) == (20, 19)
    assert client.rate_limit.reset_ms == 1700000001000


def test_espera_reset_quando_limite_zerado(fake, make_client, clock):
    reset = SERVER_TIME_MS + 2000
    fake.on("GET", "/v5/market/tickers", httpx.Response(200, json=ok({"list": []}), headers={
        "X-Bapi-Limit": "20", "X-Bapi-Limit-Status": "0", "X-Bapi-Limit-Reset-Timestamp": str(reset)}))
    client = make_client()
    client.get_tickers()
    clock.sleeps.clear()
    client.get_tickers()
    assert max(clock.sleeps) == pytest.approx(2.0, abs=0.01)


def test_rate_limiter_espaca_chamadas(clock):
    limiter = RateLimiter(4, monotonic=clock.monotonic, sleep=clock.sleep)
    for _ in range(3):
        limiter.acquire()
    assert clock.sleeps == [pytest.approx(0.25), pytest.approx(0.25)]


# ---------------------------------------------------------------- velas e paginação
def test_velas_em_ordem_cronologica(fake, make_client):
    h = 3_600_000
    rows = [[str(SERVER_TIME_MS - i * h), "10", "11", "9", "10.5", "100", "1000"] for i in range(3)]
    fake.on("GET", "/v5/market/kline", ok({"list": rows}))
    klines = make_client().get_klines("BTCUSDT", "60", limit=3)
    assert [k.start_ms for k in klines] == sorted(k.start_ms for k in klines)
    assert klines[-1].close == 10.5
    assert not klines[-1].is_closed(SERVER_TIME_MS + 10)
    assert klines[-2].is_closed(SERVER_TIME_MS + 10)


def test_velas_validam_parametros(make_client):
    client = make_client()
    with pytest.raises(ValueError):
        client.get_klines("BTCUSDT", "7")
    with pytest.raises(ValueError):
        client.get_klines("BTCUSDT", "60", limit=1001)


def test_paginacao_por_cursor(fake, make_client):
    fake.on(
        "GET",
        "/v5/order/realtime",
        ok({"list": [{"orderId": "1", "orderStatus": "New"}], "nextPageCursor": "c2"}),
        ok({"list": [{"orderId": "2", "orderStatus": "PartiallyFilled"}], "nextPageCursor": ""}),
    )
    orders = make_client().get_open_orders(symbol="BTCUSDT")
    assert [o["orderId"] for o in orders] == ["1", "2"]
    second = fake.calls("GET", "/v5/order/realtime")[1]
    assert params_of(second)["cursor"] == "c2"


def test_abertas_ignora_ordens_recem_fechadas_mas_find_order_as_encontra(fake, make_client):
    # Consultando por orderLinkId, a Bybit devolve também ordens fechadas há pouco (visto na conta demo)
    fake.on("GET", "/v5/order/realtime", ok({"list": [{"orderId": "9", "orderStatus": "Cancelled"}]}))
    client = make_client()
    assert client.get_open_orders(symbol="BTCUSDT", order_link_id="link-1") == []
    assert client.find_order("BTCUSDT", "link-1")["orderStatus"] == "Cancelled"
    assert fake.calls("GET", "/v5/order/history") == []


def test_find_order_cai_no_historico(fake, make_client):
    fake.on("GET", "/v5/order/realtime", ok({"list": []}))
    fake.on("GET", "/v5/order/history", ok({"list": [{"orderId": "8", "orderStatus": "Filled"}]}))
    assert make_client().find_order("BTCUSDT", "link-1")["orderId"] == "8"


# ---------------------------------------------------------------- idempotência de ordens
def order_kwargs(**extra):
    return {"symbol": "BTCUSDT", "side": "Buy", "order_type": "Limit", "qty": "0.001", "price": "50000",
            "order_link_id": "link-1", **extra}


def test_orderlinkid_repetido_devolve_ordem_existente(fake, make_client):
    fake.on("POST", "/v5/order/create", err(110072, "OrderLinkedID is duplicate"))
    fake.on("GET", "/v5/order/realtime", ok({"list": [{"orderId": "999", "orderLinkId": "link-1"}]}))
    result = make_client().place_order(**order_kwargs())
    assert result == {"orderId": "999", "orderLinkId": "link-1"}
    assert len(fake.calls("POST", "/v5/order/create")) == 1


def test_falha_ambigua_procura_antes_de_reenviar_e_encontra(fake, make_client):
    fake.on("POST", "/v5/order/create", httpx.ReadTimeout("timeout"))
    fake.on("GET", "/v5/order/realtime", ok({"list": [{"orderId": "777", "orderLinkId": "link-1"}]}))
    result = make_client().place_order(**order_kwargs())
    assert result["orderId"] == "777"
    assert len(fake.calls("POST", "/v5/order/create")) == 1  # não reenviou


def test_falha_ambigua_sem_ordem_reenvia(fake, make_client):
    fake.on("POST", "/v5/order/create", httpx.Response(502, text="bad gateway"),
            ok({"orderId": "555", "orderLinkId": "link-1"}))
    fake.on("GET", "/v5/order/realtime", ok({"list": []}))
    fake.on("GET", "/v5/order/history", ok({"list": []}))
    result = make_client().place_order(**order_kwargs())
    assert result["orderId"] == "555"
    assert len(fake.calls("POST", "/v5/order/create")) == 2


def test_criacao_de_ordem_nao_repete_erro_de_negocio(fake, make_client):
    fake.on("POST", "/v5/order/create", err(170131, "Insufficient balance"))
    with pytest.raises(BybitInsufficientBalanceError):
        make_client().place_order(**order_kwargs())
    assert len(fake.calls("POST", "/v5/order/create")) == 1


@pytest.mark.parametrize(
    "extra, fragment",
    [
        ({"side": "Short"}, "side"),
        ({"order_type": "Stop"}, "orderType"),
        ({"price": None}, "price"),
        ({"order_link_id": ""}, "orderLinkId"),
        ({"order_link_id": "x" * 37}, "orderLinkId"),
    ],
)
def test_place_order_valida_parametros(make_client, extra, fragment):
    with pytest.raises(ValueError, match=fragment):
        make_client().place_order(**order_kwargs(**extra))


def test_cancelar_exige_identificador(make_client):
    with pytest.raises(ValueError):
        make_client().cancel_order(symbol="BTCUSDT")


def test_from_config_paper_nao_usa_chave():
    from bot.config import load_config
    from conftest import CONFIG_PATH

    class NoSecrets:
        def get(self, name, required=True):
            raise AssertionError("paper não deve ler chaves")

    client = BybitClient.from_config(load_config(CONFIG_PATH), NoSecrets(), mode="paper")
    assert client.base_url == "https://api.bybit.com"
    with pytest.raises(Exception, match="sem chave"):
        client.get_wallet_balance()


def test_from_config_demo_usa_url_demo():
    from bot.config import load_config
    from conftest import CONFIG_PATH

    class Secrets:
        def get(self, name, required=True):
            return {"BYBIT_API_KEY": "k" * 10, "BYBIT_API_SECRET": "s" * 10}[name]

    client = BybitClient.from_config(load_config(CONFIG_PATH), Secrets(), mode="demo")
    assert client.base_url == "https://api-demo.bybit.com"


def test_network_error_tipado(fake, make_client):
    fake.on("GET", "/v5/market/tickers", httpx.ConnectError("sem rede"))
    with pytest.raises(BybitNetworkError):
        make_client(max_retries=0).get_tickers()
