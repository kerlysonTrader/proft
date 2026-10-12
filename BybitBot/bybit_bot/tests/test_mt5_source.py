from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from bot.markets.mt5_source import Mt5Error, Mt5Reader

H = 3600
NOW_UTC = 1_791_000_000  # segundos
OFFSET = 3               # servidor UTC+3


class FakeMT5:
    TIMEFRAME_M15, TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 15, 16385, 16388, 16408
    ACCOUNT_TRADE_MODE_DEMO = 0

    def __init__(self, tick_age_s=30, has_data=True):
        self.tick_age_s = tick_age_s
        self.has_data = has_data
        self.calls = []

    def initialize(self):
        return True

    def shutdown(self):
        self.calls.append("shutdown")

    def last_error(self):
        return (-1, "erro simulado")

    def account_info(self):
        return SimpleNamespace(server="Demo-Server", company="Corretora", trade_mode=0)

    def terminal_info(self):
        return SimpleNamespace(connected=True, maxbars=100000)

    def symbol_info_tick(self, symbol):
        server_time = NOW_UTC + OFFSET * H - self.tick_age_s
        return SimpleNamespace(time=server_time, bid=1.1000, ask=1.1002)

    def symbol_info(self, symbol):
        return None if symbol == "NAOEXISTE" else SimpleNamespace(digits=5, point=0.00001, spread=12)

    def copy_rates_from_pos(self, symbol, tf, start, count):
        self.calls.append(("rates", symbol, tf, count))
        if not self.has_data:
            return None
        step = {15: 900, 16385: H}[tf]
        last_open_server = (NOW_UTC + OFFSET * H) // step * step  # vela em formação (hora do servidor)
        times = [last_open_server - k * step for k in range(4, -1, -1)]
        dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                 ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")]
        return np.array([(t, 1.0, 1.2, 0.9, 1.1, 100, 12, 0) for t in times], dtype=dtype)


def reader(api) -> Mt5Reader:
    return Mt5Reader(fallback_offset_hours=2, max_bars=1000, api=api, clock=lambda: NOW_UTC)


def test_fuso_detectado_pelo_tick_recente():
    r = reader(FakeMT5())
    assert r.detect_offset(["EURUSD.s"]) == 3


def test_mercado_fechado_usa_fuso_do_config():
    r = reader(FakeMT5(tick_age_s=3 * 24 * H))  # fim de semana: último tick há 3 dias
    assert r.detect_offset(["EURUSD.s"]) == 2


def test_velas_em_utc_e_sem_a_vela_em_formacao():
    api = FakeMT5()
    r = reader(api)
    r.detect_offset(["EURUSD.s"])
    klines = r.rates("EURUSD.s", "15", count=5)
    assert len(klines) == 4  # a 5ª (em formação) foi descartada
    assert all(k.start_ms + 900_000 <= NOW_UTC * 1000 for k in klines)
    last_server_open = (NOW_UTC + OFFSET * H) // 900 * 900 - 900
    assert klines[-1].start_ms == (last_server_open - OFFSET * H) * 1000  # convertido para UTC
    assert klines[-1].turnover == pytest.approx(100 * 1.1)
    assert api.calls[0] == ("rates", "EURUSD.s", 15, 5)


def test_limite_de_barras_do_terminal():
    api = FakeMT5()
    reader(api).rates("EURUSD.s", "60", count=10**7)
    assert api.calls[0][3] == 999  # máx. barras − 1


def test_sem_dados_vira_erro_tipado():
    with pytest.raises(Mt5Error):
        reader(FakeMT5(has_data=False)).rates("EURUSD.s", "15")


def test_meta_e_spread():
    m = reader(FakeMT5()).meta("EURUSD.s")
    assert m.spread_price == pytest.approx(0.00012)
    assert m.spread_pct() == pytest.approx(0.00012 / 1.1001 * 100)
    assert reader(FakeMT5()).meta("NAOEXISTE") is None


def test_contexto_fecha_a_ligacao():
    api = FakeMT5()
    with reader(api):
        pass
    assert api.calls == ["shutdown"]
