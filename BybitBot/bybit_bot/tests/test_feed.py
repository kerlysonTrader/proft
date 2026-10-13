from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from test_structure import frame, path

from bot.bybit.client import KLINE_INTERVAL_MS
from bot.config import load_config
from bot.signals.direction import invert_frame
from bot.signals.feed import FeedState, plan_events, send_events, structure_events
from bot.signals.structure import StructureParams, structure_arrays
from conftest import CONFIG_PATH

M15, H1 = KLINE_INTERVAL_MS["15"], KLINE_INTERVAL_MS["60"]
START = 1_760_000_000_000


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_PATH)


def uptrend_frames():
    """15m em alta terminando EXATAMENTE na vela de um BOS de alta; 1H em alta (Dow) acima da MME50."""
    legs = [100, 108, 104, 112, 108, 116, 112, 120, 116, 124]
    m15 = frame(path(legs, steps=8), start_ms=START, step=M15)
    arr = structure_arrays(m15, StructureParams(pivot_bars=3))
    hits = [int(i) for i in np.flatnonzero(arr["bos_up"]) if arr["trend"][i] == 1 and i >= 60]
    m15 = m15.iloc[:hits[-1] + 1]
    now = int(m15["start_ms"].iat[-1]) + M15
    h1 = frame(path(legs, steps=8), step=H1)
    h1["start_ms"] = h1["start_ms"] - h1["start_ms"].iat[0] + (now - len(h1) * H1)   # última vela 1H já fechada
    return m15, h1, now


def test_gatilho_de_compra_a_favor_do_1h(cfg):
    m15, h1, now = uptrend_frames()
    events = structure_events("cripto", "TESTUSDT", "TESTUSDT", m15, h1, now, cfg, directions=(1,),
                              scores={1: 72.0})
    assert len(events) == 1
    e = events[0]
    assert e.kind == "gatilho" and e.direction == 1 and e.stop < e.entry < e.tp1 < e.tp2
    assert "alta" in e.description and e.context.startswith("1H em alta")
    p = e.payload()
    assert p["status"] == "gatilho" and p["symbol"] == "TESTUSDT · compra" and p["score"] == 72.0
    assert p["details"]["mercado"] == "cripto" and p["details"]["lado"] == "compra" and p["rr"] > 0
    assert "sem vantagem" in p["details"]["nota"]


def test_gatilho_de_venda_no_espelho(cfg):
    m15, h1, now = uptrend_frames()
    down15, down1h = invert_frame(m15), invert_frame(h1)          # o mesmo gráfico, de cabeça para baixo
    events = structure_events("mt5", "XAUUSD", "XAUUSD.s", down15, down1h, now, cfg, directions=(1, -1))
    assert [e.direction for e in events] == [-1]
    e = events[0]
    assert e.side == "venda" and e.stop > e.entry > e.tp1 > e.tp2
    assert "baixa" in e.description and e.payload()["symbol"] == "XAUUSD · venda"


def test_sem_gatilho_contra_o_1h(cfg):
    m15, h1, now = uptrend_frames()
    assert structure_events("cripto", "T", "T", m15, invert_frame(h1), now, cfg, directions=(1,)) == []


def plan(situacao, **kw):
    base = {"setup": "Pullback", "lado": "compra", "entrada": 10.0, "stop": 9.5, "tp1": 10.75, "tp2": 11.5,
            "zona": [9.8, 10.0], "situacao": situacao, "gatilho": "vela 15m fechando acima da EMA20", "alerta": False}
    return {**base, **kw}


def test_mudanca_dos_planos():
    state = FeedState()
    assert plan_events("cripto", "X", 1, [plan("aguardando")], state, START) == []     # 1ª vez: só registra
    ev = plan_events("cripto", "X", 1, [plan("na_zona")], state, START + M15)
    assert [e.kind for e in ev] == ["na_zona"] and "entrou na zona" in ev[0].description
    assert plan_events("cripto", "X", 1, [plan("na_zona")], state, START + 2 * M15) == []   # sem mudança
    ev = plan_events("cripto", "X", 1, [plan("invalidado", retomada=10.0)], state, START + 3 * M15)
    assert [e.kind for e in ev] == ["invalidado"] and "voltar acima" in ev[0].description
    assert ev[0].setup == "pullback_tendencia"


def test_cada_evento_vai_uma_vez(tmp_path, cfg):
    m15, h1, now = uptrend_frames()
    events = structure_events("cripto", "T", "T", m15, h1, now, cfg, directions=(1,))
    sent = []
    dashboard = SimpleNamespace(send=lambda kind, payload: sent.append((kind, payload)) or SimpleNamespace(ok=True))
    state = FeedState()
    assert send_events(events, state, dashboard) == (1, 0)
    assert send_events(events, state, dashboard) == (0, 0)
    state.save(tmp_path / "feed.json")
    again = FeedState.load(tmp_path / "feed.json")
    assert send_events(events, again, dashboard) == (0, 0) and len(sent) == 1
    assert sent[0][0] == "signal"


# ------------------------------------------------------------------ placar dos gatilhos
def candles_after(rows, start=START):
    import pandas as pd

    return pd.DataFrame([{"start_ms": start + i * M15, "open": o, "high": h, "low": low, "close": c}
                         for i, (o, h, low, c) in enumerate(rows)])


TRACK = {"dir": 1, "entrada": 100.0, "stop": 98.0, "tp1": 103.0, "tp2": 106.0, "inicio_ms": START}


@pytest.mark.parametrize("rows, expected, r", [
    ([(100, 101, 99.5, 100.5), (100.5, 103.2, 100, 103)], "alvo", 1.5),        # alvo 1 primeiro
    ([(100, 100.5, 97.9, 98.5)], "stop", -1.0),                                 # stop primeiro
    ([(100, 103.5, 97.5, 101)], "stop", -1.0),                                  # os dois na mesma vela: stop
])
def test_resultado_do_gatilho(rows, expected, r):
    from bot.signals.feed import resolve

    res = resolve(TRACK, candles_after(rows), START + 10 * M15)
    assert res["resultado"] == expected and res["resultado_r"] == r


def test_gatilho_em_aberto_e_expirado():
    from bot.signals.feed import TRACK_HOURS, resolve

    rows = [(100, 101, 99.5, 101)] * 4
    assert resolve(TRACK, candles_after(rows), START + 4 * M15) is None
    res = resolve(TRACK, candles_after(rows), START + int(TRACK_HOURS * 3_600_000))
    assert res["resultado"] == "expirou" and res["resultado_r"] == 0.5


def test_venda_espelhada():
    from bot.signals.feed import resolve

    track = {"dir": -1, "entrada": 100.0, "stop": 102.0, "tp1": 97.0, "tp2": 94.0, "inicio_ms": START}
    res = resolve(track, candles_after([(100, 100.5, 96.8, 97)]), START + M15)
    assert res["resultado"] == "alvo" and res["resultado_r"] == 1.5


def test_placar_envia_resultado_e_encerra(cfg):
    from bot.signals.feed import update_tracking

    m15, h1, now = uptrend_frames()
    events = structure_events("cripto", "T", "T", m15, h1, now, cfg, directions=(1,))
    sent = []
    dashboard = SimpleNamespace(send=lambda kind, payload: sent.append(payload) or SimpleNamespace(ok=True))
    state = FeedState()
    send_events(events, state, dashboard)
    assert list(state.tracking) == [events[0].event_id] and sent[0]["details"]["resultado"] == "aberto"
    e = events[0]
    rows = [(e.entry, e.tp1 * 1.001, e.entry * 0.9999, e.tp1)]          # alvo na vela seguinte
    closed = update_tracking(state, lambda s: candles_after(rows, start=now), now + 2 * M15, dashboard)
    assert closed == 1 and state.tracking == {}
    final = sent[-1]
    assert final["order_link_id"] == e.event_id and final["details"]["resultado"] == "alvo"
    assert final["details"]["resultado_r"] == pytest.approx(cfg.exits.tp1_r, abs=0.01)
