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
