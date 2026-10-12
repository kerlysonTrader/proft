from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bot.bybit.client import KLINE_INTERVAL_MS
from bot.config import load_config
from bot.signals.structure import StructureParams, reading_lines, row_at, structure_arrays
from bot.signals.structure_setups import (
    STRUCTURE_SETUPS,
    TRIGGER_KEY,
    context_ok,
    structure_signals,
    structure_signals_live,
)
from conftest import CONFIG_PATH

M15 = KLINE_INTERVAL_MS["15"]
P = StructureParams(pivot_bars=3)


def frame(closes, start_ms=1_760_000_000_000, step=M15, wick=0.1) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    opens = closes.copy()   # sem gap: o topo de uma perna não empata com a vela seguinte
    return pd.DataFrame({"start_ms": start_ms + np.arange(len(closes)) * step, "open": opens,
                         "high": np.maximum(opens, closes) + wick, "low": np.minimum(opens, closes) - wick,
                         "close": closes, "volume": 100.0, "turnover": 100.0 * closes})


def path(points, steps=8):
    """Segmentos de reta entre os pontos (cada perna com `steps` velas)."""
    out = [points[0]]
    for a, b in zip(points, points[1:], strict=False):
        out += list(np.linspace(a, b, steps + 1)[1:])
    return out


def first(arrays, key):
    hits = np.flatnonzero(arrays[key])
    return int(hits[0]) if len(hits) else None


def bos_in_uptrend(arr):
    hits = [int(i) for i in np.flatnonzero(arr["bos_up"]) if arr["trend"][i] == 1]
    return hits[0] if hits else None


def test_dow_em_alta_e_bos():
    arr = structure_arrays(frame(path([100, 110, 105, 115, 110, 120])), P)
    i = bos_in_uptrend(arr)   # o 1º BOS acontece com só 1 topo/1 fundo confirmados (lateral)
    assert i is not None and arr["trend"][i] == 1
    assert arr["break_level"][i] == pytest.approx(115.1)
    assert arr["close"][i] > 115.1 >= arr["close"][i - 1]
    assert not arr["choch_up"].any()


def test_choch_na_virada_de_baixa_para_alta():
    arr = structure_arrays(frame(path([120, 110, 115, 105, 110, 104, 113])), P)
    i = first(arr, "choch_up")
    assert i is not None and arr["trend"][i] == -1          # quebrou o último topo DENTRO de uma baixa
    assert arr["break_level"][i] == pytest.approx(110.1)


def test_choch_de_baixa_perde_o_fundo_que_sustentava_a_alta():
    arr = structure_arrays(frame(path([100, 110, 105, 115, 110, 120, 104])), P)
    i = first(arr, "choch_down")
    assert i is not None and arr["trend"][i] == 1
    assert arr["break_level"][i] == pytest.approx(109.9)


def test_ltb_e_cunha_de_baixa_rompendo_para_cima():
    pts = [120, 100, 114, 98, 108, 96.5, 112]   # topos caem rápido, fundos devagar
    arr = structure_arrays(frame(path(pts, steps=10)), P)
    i = first(arr, "ltb_break")
    assert i is not None and arr["wedge_up"][i]
    assert arr["close"][i] > arr["ltb"][i]
    assert arr["ltb_touches"][i] >= 2
    assert first(arr, "wedge_up") == i


def test_ltb_sem_cunha_quando_fundos_sobem():
    pts = [120, 100, 114, 102, 108, 104, 112]   # topos descendentes, fundos ascendentes = triângulo
    arr = structure_arrays(frame(path(pts, steps=10)), P)
    i = first(arr, "ltb_break")
    assert i is not None and not arr["wedge_up"][i]


def test_cruzamento_das_medias():
    closes = list(np.linspace(110, 100, 60)) + list(np.linspace(100, 112, 60))
    arr = structure_arrays(frame(closes), P)
    diff = arr["ema_fast"] - arr["ema_slow"]
    expected = np.flatnonzero((diff[1:] > 0) & (diff[:-1] <= 0)) + 1
    assert list(np.flatnonzero(arr["cross_up"])) == list(expected) and len(expected) == 1


def random_walk(n=1600, seed=7):
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    return frame(closes, wick=0.05)


def test_sem_olhar_o_futuro():
    """A leitura de uma vela não muda quando velas futuras chegam."""
    df = random_walk()
    full = structure_arrays(df, P)
    for k in (250, 401, 777, 1200, 1599):
        part = structure_arrays(df.iloc[:k], P)
        for key in full:
            np.testing.assert_array_equal(full[key][:k], part[key], err_msg=f"{key} até {k}")


def test_leitura_em_texto():
    arr = structure_arrays(frame(path([100, 110, 105, 115, 110, 120])), P)
    lines = reading_lines(row_at(arr, len(arr["close"]) - 1), None, "15m", "1H")
    assert lines[0].startswith("Estrutura 15m: alta (Dow)")
    assert any(x.startswith("Médias 15m:") for x in lines)


# ------------------------------------------------------------------ setups
@pytest.fixture(scope="module")
def cfg():
    c = load_config(CONFIG_PATH)
    st = c.setups.model_copy(update={"enabled": list(STRUCTURE_SETUPS), "trigger_interval": "15",
                                     "context_interval": "60",
                                     "estrutura": c.setups.estrutura.model_copy(update={"context": "dow"})})
    return c.model_copy(update={"setups": st})


def test_contexto():
    base = {"trend": 1, "close": 10.0, "ema_mid": 9.0, "ema_slow": 9.5}
    assert context_ok(base, "dow_e_media") and context_ok(base, "dow") and context_ok(base, "media")
    assert not context_ok({**base, "close": 8.0}, "dow_e_media") and context_ok({**base, "close": 8.0}, "dow")
    assert not context_ok({**base, "trend": 0}, "dow")


def test_sinal_de_bos_com_stop_no_ultimo_fundo(cfg):
    arr = structure_arrays(frame(path([100, 110, 105, 115, 110, 120])), P)
    i = bos_in_uptrend(arr)
    t = row_at(arr, i)
    ctx = {"trend": 1, "close": 120.0, "ema_mid": 110.0, "ema_slow": 112.0}
    sigs = structure_signals("X", t, ctx, 0, 70.0, cfg, ["estrutura_bos"])
    assert len(sigs) == 1
    s = sigs[0]
    assert s.setup == "estrutura_bos" and s.stop < t["last_low"] < s.entry < s.tp1 < s.tp2
    assert (s.tp2 - s.entry) / (s.entry - s.stop) == pytest.approx(cfg.exits.tp2_r)
    assert structure_signals("X", t, {**ctx, "trend": -1}, 0, 70.0, cfg, ["estrutura_bos"]) == []


def test_robo_ao_vivo_e_backtest_dao_os_mesmos_sinais(cfg):
    """Caminho rápido do backtest (série inteira pré-calculada) == cálculo ao vivo sobre as velas até ali."""
    trig = random_walk(2400, seed=11)
    ctx = (trig.assign(t=pd.to_datetime(trig["start_ms"], unit="ms")).set_index("t")
           .resample("1h").agg({"start_ms": "first", "open": "first", "high": "max", "low": "min", "close": "last",
                                "volume": "sum", "turnover": "sum"}).dropna().reset_index(drop=True))
    params = StructureParams.from_config(cfg.setups.estrutura, cfg.indicators.atr_period)
    full_t, full_c = structure_arrays(trig, params), structure_arrays(ctx, params)
    ctx_ends = ctx["start_ms"].to_numpy() + KLINE_INTERVAL_MS["60"]
    keys = [TRIGGER_KEY[s] for s in STRUCTURE_SETUPS]
    positions = [i for i in range(400, len(trig)) if any(full_t[k][i] for k in keys)]
    assert len(positions) > 20
    compared = 0
    for pos in positions[:60]:
        now = int(trig["start_ms"].iat[pos]) + M15
        k = int(np.searchsorted(ctx_ends, now, side="right")) - 1
        fast = structure_signals("X", row_at(full_t, pos), row_at(full_c, k), int(trig["start_ms"].iat[pos]),
                                 50.0, cfg, list(STRUCTURE_SETUPS))
        live = structure_signals_live("X", trig.iloc[:pos + 1], ctx.iloc[:k + 1], now, 50.0, cfg)
        assert [(s.setup, round(s.entry, 9), round(s.stop, 9)) for s in fast] == \
               [(s.setup, round(s.entry, 9), round(s.stop, 9)) for s in live]
        compared += bool(fast)
    assert compared > 0
