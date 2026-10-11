from __future__ import annotations

import hashlib
import hmac

from bot.bybit.client import build_query, sign_payload
from conftest import API_KEY, API_SECRET, SERVER_TIME_MS, body_of, ok, query_of


def test_assinatura_segue_formato_v5():
    # Exemplo da documentação V5: timestamp + apiKey + recvWindow + queryString
    payload = "category=option&symbol=BTC-29JUL22-25000-C"
    expected_message = f"1658384314791XXXXXXXXXX5000{payload}"
    expected = hmac.new(b"segredo", expected_message.encode(), hashlib.sha256).hexdigest()
    assert sign_payload("segredo", 1658384314791, "XXXXXXXXXX", 5000, payload) == expected
    assert len(expected) == 64


def test_query_mantem_ordem_e_remove_none():
    assert build_query({"category": "spot", "symbol": None, "limit": 50, "openOnly": 0}) == \
        "category=spot&limit=50&openOnly=0"
    assert build_query(None) == ""


def test_get_assinado_envia_headers_e_assina_a_query_enviada(fake, make_client):
    fake.on("GET", "/v5/account/wallet-balance", ok({"list": [{"totalEquity": "1000"}]}))
    client = make_client()
    client.get_wallet_balance("UNIFIED")

    request = fake.calls("GET", "/v5/account/wallet-balance")[0]
    ts = int(request.headers["X-BAPI-TIMESTAMP"])
    assert request.headers["X-BAPI-API-KEY"] == API_KEY
    assert request.headers["X-BAPI-RECV-WINDOW"] == "5000"
    assert query_of(request) == "accountType=UNIFIED"
    assert request.headers["X-BAPI-SIGN"] == sign_payload(API_SECRET, ts, API_KEY, 5000, "accountType=UNIFIED")
    assert abs(ts - SERVER_TIME_MS) < 1000


def test_post_assinado_assina_exatamente_o_corpo_enviado(fake, make_client):
    fake.on("POST", "/v5/order/create", ok({"orderId": "1", "orderLinkId": "abc"}))
    client = make_client()
    client.place_order(symbol="BTCUSDT", side="Buy", order_type="Limit", qty="0.001", price="50000",
                       order_link_id="abc")

    request = fake.calls("POST", "/v5/order/create")[0]
    body_text = request.content.decode()
    ts = int(request.headers["X-BAPI-TIMESTAMP"])
    assert request.headers["X-BAPI-SIGN"] == sign_payload(API_SECRET, ts, API_KEY, 5000, body_text)
    body = body_of(request)
    assert body["category"] == "spot"
    assert body["qty"] == "0.001" and body["price"] == "50000"
    assert body["timeInForce"] == "GTC"
    assert "marketUnit" not in body  # campos None não são enviados


def test_chamada_publica_nao_envia_chave(fake, make_client):
    fake.on("GET", "/v5/market/tickers", ok({"list": [{"symbol": "BTCUSDT", "lastPrice": "1"}]}))
    make_client().get_tickers("BTCUSDT")
    request = fake.calls("GET", "/v5/market/tickers")[0]
    assert "X-BAPI-API-KEY" not in request.headers
    assert "X-BAPI-SIGN" not in request.headers
