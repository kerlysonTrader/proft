from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bot.bybit.client import KLINE_INTERVAL_MS, Kline
from bot.bybit.errors import BybitError
from bot.config import load_config
from bot.data.market_data import MarketData, OrderBook, align_start
from bot.storage.kline_store import KlineStore
from conftest import CONFIG_PATH

HOUR = KLINE_INTERVAL_MS["60"]
T0 = 1_767_225_600_000  # 2026-01-01 00:00 UTC
LISTED_AT = T0          # a "moeda" só tem velas a partir daqui


class FakeMarketClient:
    def __init__(self, now_ms: int, page_cap: int = 1000) -> None:
        self.now = now_ms
        self.page_cap = page_cap
        self.kline_calls: list[tuple] = []
        self.oi_fail = False
        self.linear = {"BTCUSDT": {"symbol": "BTCUSDT", "fundingRate": "0.0001"}}

    def now_ms(self) -> int:
        return self.now

    def get_klines(self, symbol, interval, limit=200, start_ms=None, end_ms=None, category="spot"):
        self.kline_calls.append((symbol, interval, limit, start_ms, end_ms))
        step = KLINE_INTERVAL_MS[interval]
        last = align_start(self.now, interval)  # inclui a vela em formação, como a Bybit
        end = min(end_ms if end_ms is not None else last, last)
        start = max(start_ms if start_ms is not None else LISTED_AT, LISTED_AT)
        starts = list(range(align_start(end, interval), start - 1, -step))[: min(limit, self.page_cap)]
        return [Kline(s, interval, 1.0, 2.0, 0.5, 1.5, 10.0, 15.0, symbol) for s in sorted(starts)]

    def get_tickers(self, symbol=None, category="spot"):
        if category == "linear":
            return list(self.linear.values())
        return [{"symbol": "BTCUSDT", "lastPrice": "100"}]

    def get_orderbook(self, symbol, limit=200, category="spot"):
        return {"b": [["99", "10"], ["98.5", "10"], ["96", "100"]], "a": [["101", "5"]], "ts": self.now}

    def get_open_interest(self, symbol, interval_time="1h", limit=25, category="linear"):
        if self.oi_fail:
            raise BybitError("fora do ar")
        values = [110.0] + [105.0] * (limit - 2) + [100.0]  # mais novo primeiro: 100 -> 110 em 24h
        return [{"openInterest": str(v), "timestamp": "0"} for v in values]

    def get_account_ratio(self, symbol, period="1h", limit=1, category="linear"):
        return [{"buyRatio": "0.6", "sellRatio": "0.4"}]


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def cfg():
    return load_config(CONFIG_PATH).market_data


def make(cfg, client, store=None, clock=None):
    return MarketData(client, cfg, store=store, clock=clock or Clock(), now_ms=client.now_ms)


def test_align_start_diario_e_semanal():
    t = int(datetime(2026, 10, 14, 15, 30, tzinfo=UTC).timestamp() * 1000)  # quarta-feira
    assert align_start(t, "D") == int(datetime(2026, 10, 14, tzinfo=UTC).timestamp() * 1000)
    assert align_start(t, "W") == int(datetime(2026, 10, 12, tzinfo=UTC).timestamp() * 1000)  # segunda
    assert align_start(t, "240") == int(datetime(2026, 10, 14, 12, tzinfo=UTC).timestamp() * 1000)


def test_klines_so_velas_fechadas_e_em_ordem(cfg):
    client = FakeMarketClient(now_ms=T0 + 500 * HOUR + 30 * 60_000)  # meio da vela 500
    df = make(cfg, client).klines("BTCUSDT", "60", limit=100)
    assert len(df) == 100
    assert df["start_ms"].is_monotonic_increasing
    assert df["start_ms"].iloc[-1] == T0 + 499 * HOUR  # a vela 500 (em formação) fica de fora
    assert str(df.index.tz) == "UTC"


def test_klines_respeita_folga_depois_do_fechamento(cfg):
    client = FakeMarketClient(now_ms=T0 + 500 * HOUR + 2_000)  # 2 s depois de fechar; folga = 5 s
    df = make(cfg, client).klines("BTCUSDT", "60", limit=10)
    assert df["start_ms"].iloc[-1] == T0 + 498 * HOUR


def test_paginacao_de_1000_em_1000(cfg):
    client = FakeMarketClient(now_ms=T0 + 3000 * HOUR + 60_000)
    df = make(cfg, client).klines("BTCUSDT", "60", limit=2500)
    assert len(df) == 2500
    assert len(client.kline_calls) == 3
    assert df["start_ms"].diff().dropna().eq(HOUR).all()  # sem buracos nem duplicadas


def test_cache_ate_a_proxima_vela(cfg):
    client = FakeMarketClient(now_ms=T0 + 500 * HOUR + 60_000)
    md = make(cfg, client)
    md.klines("BTCUSDT", "60", limit=50)
    calls = len(client.kline_calls)
    md.klines("BTCUSDT", "60", limit=50)
    assert len(client.kline_calls) == calls  # mesma vela: cache
    client.now += HOUR
    df = md.klines("BTCUSDT", "60", limit=50)
    assert len(client.kline_calls) == calls + 1
    assert df["start_ms"].iloc[-1] == T0 + 500 * HOUR


def test_historico_persistido_busca_so_o_que_falta(cfg, tmp_path):
    store = KlineStore(tmp_path / "m.db")
    client = FakeMarketClient(now_ms=T0 + 500 * HOUR + 60_000)
    make(cfg, client, store).klines("BTCUSDT", "60", limit=200)
    assert store.bounds("BTCUSDT", "60")[2] == 200

    client.now += 3 * HOUR
    client.kline_calls.clear()
    df = make(cfg, client, store).klines("BTCUSDT", "60", limit=200)  # novo processo, mesmo banco
    assert len(client.kline_calls) == 1
    _, _, _, start, end = client.kline_calls[0]
    assert (start, end) == (T0 + 500 * HOUR, T0 + 502 * HOUR)  # só as 3 velas novas
    assert df["start_ms"].iloc[-1] == T0 + 502 * HOUR
    assert len(df) == 200


def test_moeda_nova_devolve_o_que_existe_e_nao_rebusca_o_inicio(cfg):
    client = FakeMarketClient(now_ms=T0 + 30 * HOUR + 60_000)
    md = make(cfg, client)
    df = md.klines("NOVAUSDT", "60", limit=300)
    assert len(df) == 30
    client.now += HOUR
    client.kline_calls.clear()
    md.klines("NOVAUSDT", "60", limit=300)
    assert len(client.kline_calls) == 1
    assert client.kline_calls[0][3] >= LISTED_AT  # não pede de novo o período antes da listagem


def test_intervalo_invalido(cfg):
    with pytest.raises(ValueError):
        make(cfg, FakeMarketClient(T0)).klines("BTCUSDT", "7")


def test_livro_de_ofertas(cfg):
    book = make(cfg, FakeMarketClient(T0)).orderbook("BTCUSDT")
    assert isinstance(book, OrderBook)
    assert book.mid == 100
    assert book.spread_pct == pytest.approx(2.0)
    # até −2 % do meio (>= 98): 99*10 + 98.5*10
    assert book.bid_depth_quote(2) == pytest.approx(1975)


def test_tickers_com_ttl(cfg):
    clock = Clock()
    client = FakeMarketClient(T0)
    calls = []
    original = client.get_tickers
    client.get_tickers = lambda *a, **k: calls.append(1) or original(*a, **k)
    md = make(cfg, client, clock=clock)
    md.spot_tickers()
    md.spot_tickers()
    assert len(calls) == 1
    clock.t += cfg.cache_ttl_seconds.tickers + 1
    md.spot_tickers()
    assert len(calls) == 2


def test_derivativos_com_perpetuo(cfg):
    snap = make(cfg, FakeMarketClient(T0)).derivatives("BTCUSDT")
    assert snap.funding_rate_pct == pytest.approx(0.01)
    assert snap.open_interest == 110
    assert snap.oi_change_pct == pytest.approx(10.0)
    assert snap.long_short_ratio == pytest.approx(1.5)


def test_derivativos_sem_perpetuo_e_none(cfg):
    assert make(cfg, FakeMarketClient(T0)).derivatives("SEMPERPUSDT") is None


def test_falha_no_open_interest_vira_ausente(cfg):
    client = FakeMarketClient(T0)
    client.oi_fail = True
    snap = make(cfg, client).derivatives("BTCUSDT")
    assert snap.open_interest is None and snap.oi_change_pct is None
    assert snap.long_short_ratio == pytest.approx(1.5)  # o resto continua


def test_kline_store_upsert_idempotente(tmp_path):
    store = KlineStore(tmp_path / "k.db")
    klines = [Kline(T0 + i * HOUR, "60", 1, 2, 0.5, 1.5, 10, 15, "ETHUSDT") for i in range(5)]
    assert store.upsert(klines) == 5
    store.upsert(klines[2:])
    assert store.bounds("ETHUSDT", "60") == (T0, T0 + 4 * HOUR, 5)
    loaded = store.load("ETHUSDT", "60", T0 + HOUR, T0 + 3 * HOUR)
    assert [k.start_ms for k in loaded] == [T0 + HOUR, T0 + 2 * HOUR, T0 + 3 * HOUR]
    assert loaded[0].symbol == "ETHUSDT"
    assert store.symbols("60") == ["ETHUSDT"]
