from __future__ import annotations

import pandas as pd
import pytest

from bot.config import load_config
from bot.signals.base import Signal, closed_only
from bot.signals.breakout import breakout_signal
from bot.signals.engine import evaluate, signal_payload
from bot.signals.filters import SignalContext, check_filters
from bot.signals.ote_fibo import find_pivots, last_leg, ote_signal, zigzag
from bot.signals.pullback import pullback_signal
from conftest import CONFIG_PATH

H = 3_600_000


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_PATH)


def candles(rows, start="2026-01-01", freq="h", volume=100.0) -> pd.DataFrame:
    """rows = [(open, high, low, close)] ou [(open, high, low, close, volume)]."""
    data = [r if len(r) == 5 else (*r, volume) for r in rows]
    df = pd.DataFrame(data, columns=["open", "high", "low", "close", "volume"],
                      index=pd.date_range(start, periods=len(data), freq=freq, tz="UTC"))
    df.insert(0, "start_ms", [int(ts.timestamp() * 1000) for ts in df.index])
    df["turnover"] = df["close"] * df["volume"]
    return df


def path(closes, start_price=None, wick=0.001):
    """Velas a partir de uma sequência de fechamentos (abertura = fechamento anterior)."""
    rows, prev = [], start_price if start_price is not None else closes[0]
    for c in closes:
        rows.append((prev, max(prev, c) * (1 + wick), min(prev, c) * (1 - wick), c))
        prev = c
    return rows


def end_ms(df: pd.DataFrame, interval_ms: int = H) -> int:
    return int(df["start_ms"].iloc[-1]) + interval_ms


# ------------------------------------------------------------------ pullback_tendencia
def pullback_closes(pullback_steps=5, step=-0.008, confirm=0.03):
    closes, p = [], 100.0
    for i in range(100):  # tendência de alta com respiros (RSI ~70)
        p *= 1.008 if i % 2 == 0 else 0.997
        closes.append(p)
    for _ in range(pullback_steps):
        p *= 1 + step
        closes.append(p)
    closes.append(p * (1 + confirm))  # vela de confirmação
    return closes


def h4_for(h1: pd.DataFrame) -> pd.DataFrame:
    """4H coerente com o 1H (agregação), só para o toque na EMA20 4H."""
    agg = h1.resample("4h").agg({"start_ms": "first", "open": "first", "high": "max", "low": "min",
                                 "close": "last", "volume": "sum", "turnover": "sum"})
    return agg.dropna()


def run_pullback(cfg, h1, trend=25, now=None):
    return pullback_signal("PBUSDT", h1, h4_for(h1), now or end_ms(h1), trend, 80, cfg.setups.pullback_tendencia,
                           cfg.indicators, cfg.exits)


def test_pullback_dispara(cfg):
    h1 = candles(path(pullback_closes()))
    s = run_pullback(cfg, h1)
    assert s is not None and s.setup == "pullback_tendencia"
    assert s.entry == pytest.approx(h1["close"].iloc[-1] * 1.001)
    assert s.stop < h1["low"].iloc[-7:].min()
    assert s.rr == pytest.approx(cfg.exits.tp2_r)
    assert s.tp1 == pytest.approx(s.entry + cfg.exits.tp1_r * s.risk)
    assert s.candle_start_ms == h1["start_ms"].iloc[-1]
    assert check_filters(s, SignalContext(end_ms(h1), spread_pct={"PBUSDT": 0.05}), cfg.setups.common, 0.15) == []


def test_pullback_nao_dispara_com_a_vela_em_formacao(cfg):
    h1 = candles(path(pullback_closes()))
    forming = end_ms(h1) - 10 * 60_000  # a vela de confirmação ainda tem 10 min pela frente
    assert run_pullback(cfg, h1, now=forming) is None


def test_pullback_exige_tendencia(cfg):
    assert run_pullback(cfg, candles(path(pullback_closes())), trend=12) is None


def test_pullback_sem_confirmacao_forte(cfg):
    assert run_pullback(cfg, candles(path(pullback_closes(confirm=0.001)))) is None


def test_pullback_queda_funda_demais(cfg):
    # 12 velas de −1,2 %: RSI fura 35 e o preço perde a EMA50
    assert run_pullback(cfg, candles(path(pullback_closes(pullback_steps=11, step=-0.012)))) is None


def test_pullback_sem_recuo(cfg):
    # sem recuo: só alta e a "confirmação"
    assert run_pullback(cfg, candles(path(pullback_closes(pullback_steps=0)))) is None


# ------------------------------------------------------------------ rompimento_compressao
def breakout_frames(last_close=102.0, prev_close=100.5, last_volume=300.0):
    h4 = candles([(100, 101, 99, 100)] * 40, start="2025-12-29", freq="4h")
    rows = [(100, 100.5, 99.5, 100, 100.0)] * 98
    rows.append((100, 100.8, 99.8, prev_close, 100.0))
    rows.append((prev_close, max(prev_close, last_close) + 0.2, prev_close - 0.1, last_close, last_volume))
    h1 = candles(rows, start="2026-01-01")
    return h1, h4


def run_breakout(cfg, h1, h4, squeeze=15, now=None):
    return breakout_signal("BOUSDT", h1, h4, now or end_ms(h1), squeeze, 75, cfg.setups.rompimento_compressao,
                           cfg.indicators, cfg.exits)


def test_rompimento_dispara_e_entra_no_reteste(cfg):
    h1, h4 = breakout_frames()
    s = run_breakout(cfg, h1, h4)
    assert s is not None
    assert s.extra["level"] == 101
    assert s.entry == pytest.approx(101 * 1.002)            # reteste do nível + 0,2 %
    assert s.stop == pytest.approx(100.0)                    # meio do range (mais perto que nível − 1,5 ATR)
    assert s.valid_candles == 6
    assert s.rr == pytest.approx(cfg.exits.tp2_r)


@pytest.mark.parametrize(
    "kwargs, squeeze",
    [
        ({"last_volume": 120.0}, 15),     # volume fraco
        ({"last_close": 100.9}, 15),      # não fechou acima do nível
        ({"prev_close": 101.5}, 15),      # rompimento antigo (a anterior já tinha fechado acima)
        ({}, 8),                          # compressão insuficiente no score
    ],
)
def test_rompimento_nao_dispara(cfg, kwargs, squeeze):
    h1, h4 = breakout_frames(**kwargs)
    assert run_breakout(cfg, h1, h4, squeeze=squeeze) is None


def test_rompimento_nao_dispara_com_a_vela_em_formacao(cfg):
    h1, h4 = breakout_frames()
    assert run_breakout(cfg, h1, h4, now=end_ms(h1) - 60_000) is None


def test_rompimento_respeita_distancia_minima_do_stop(cfg):
    h4 = candles([(100, 100.2, 99.9, 100)] * 40, start="2025-12-29", freq="4h")  # range estreito
    rows = [(100, 100.9, 99.1, 100, 100.0)] * 98 + [(100, 100.1, 99.9, 100.1, 100.0),
                                                   (100.1, 101.5, 100, 101.2, 400.0)]
    h1 = candles(rows)
    s = run_breakout(cfg, h1, h4)
    assert s is not None
    from bot.indicators import atr
    atr_now = atr(h1, cfg.indicators.atr_period).iloc[-1]
    assert s.entry - s.stop >= cfg.setups.rompimento_compressao.min_stop_atr * atr_now - 1e-9


# ------------------------------------------------------------------ ote_fibo
def ote_rows():
    rows = [(100, 100.5, 99.5, 100)] * 30                    # 0–29 lateral
    rows += [(100, 100.2, 95, 99),                            # 30: fundo (origem da perna)
             (99, 101, 97, 97.5),                             # 31: última vela de baixa = Order Block
             (97.5, 102.8, 97.3, 102.5)]                      # 32: deslocamento (corpo 5)
    rows += [(102.5, 103.8, 102.3, 103.5), (103.5, 105, 103.3, 104.8), (104.8, 106.5, 104.6, 106.2),
             (106.2, 108, 106, 107.8), (107.8, 109.5, 107.6, 109.2), (109.2, 110, 109, 109.5)]  # 33–38: topo 110
    rows += [(109.5, 109.8, 107.8, 108), (108, 108.3, 106.3, 106.5), (106.5, 106.8, 104.8, 105),
             (105, 105.3, 103.3, 103.5), (103.5, 103.8, 102, 102.2), (102.2, 102.5, 101, 101.2)]  # 39–44: recuo
    rows += [(101.2, 101.9, 99.5, 101.5)]                    # 45: toca a zona e fecha acima (rejeição)
    return rows


def run_ote(cfg, h1, now=None, **cfg_overrides):
    oc = cfg.setups.ote_fibo.model_copy(update=cfg_overrides) if cfg_overrides else cfg.setups.ote_fibo
    return ote_signal("OTEUSDT", h1, now or end_ms(h1), 72, oc, cfg.indicators)


def test_fractais_e_perna(cfg):
    h1 = candles(ote_rows())
    leg = last_leg(h1, 5)
    assert leg is not None and leg.bullish
    assert (leg.start.pos, leg.start.price, leg.end.pos, leg.end.price) == (30, 95, 38, 110)
    assert leg.price_at(0) == 110 and leg.price_at(1) == 95
    assert zigzag(find_pivots(h1, 5))[-1].is_high


def test_ote_dispara_na_rejeicao(cfg):
    h1 = candles(ote_rows())
    s = run_ote(cfg, h1)
    assert s is not None and s.setup == "ote_fibo"
    assert s.extra["order_block"] == (97, 101)
    zone_low, zone_high = s.extra["zone"]
    assert zone_low == pytest.approx(110 - 0.79 * 15) and zone_high == pytest.approx(110 - 0.618 * 15)
    assert s.tp1 == pytest.approx(102.5) and s.tp2 == pytest.approx(110)   # 50 % da perna e topo
    assert s.extra["tp3"] == pytest.approx(110 + 0.618 * 15)
    assert s.stop < 95                                                     # abaixo da origem
    # com o stop na origem, o R:R até o topo fica < 2: o filtro comum barra (correto pela regra)
    problems = check_filters(s, SignalContext(end_ms(h1), spread_pct={"OTEUSDT": 0.05}), cfg.setups.common, 0.15)
    assert any("R:R" in p for p in problems)


def test_ote_nao_dispara_com_a_vela_em_formacao(cfg):
    h1 = candles(ote_rows())
    assert run_ote(cfg, h1, now=end_ms(h1) - 60_000) is None


def test_ote_sem_fechamento_acima_da_zona(cfg):
    rows = ote_rows()
    rows[-1] = (101.2, 101.4, 99.5, 100.2)  # tocou mas fechou dentro da zona
    assert run_ote(cfg, candles(rows)) is None


def test_ote_so_a_primeira_rejeicao(cfg):
    rows = ote_rows() + [(101.5, 102, 100, 101.8)]  # segunda rejeição na vela seguinte
    assert run_ote(cfg, candles(rows)) is None


def test_ote_perna_invalidada_abaixo_da_origem(cfg):
    rows = ote_rows()
    rows[-2] = (102.2, 102.5, 94, 94.5)  # fechou abaixo da origem (95)
    rows[-1] = (94.5, 101.9, 94.4, 101.5)
    assert run_ote(cfg, candles(rows)) is None


def test_ote_exige_order_block_quando_configurado(cfg):
    rows = ote_rows()
    rows[30] = (99, 100.2, 95, 100)   # origem vira vela de alta
    rows[31] = (100, 101, 97, 100.5)  # e a 31 também: não sobra vela de baixa antes do deslocamento
    assert run_ote(cfg, candles(rows)) is None
    assert run_ote(cfg, candles(rows), use_order_block=False) is not None


def test_ote_ignora_perna_de_baixa(cfg):
    rows = [(r[3] * 0 + 200 - r[3], 200 - r[2], 200 - r[1], 200 - r[3]) for r in ote_rows()]  # espelho
    assert run_ote(cfg, candles(rows)) is None


# ------------------------------------------------------------------ filtros comuns e saída
def make_signal(**kw) -> Signal:
    base = dict(symbol="XUSDT", setup="pullback_tendencia", entry=100.0, stop=97.0, tp1=104.5, tp2=109.0,
                candle_start_ms=1_791_763_200_000, valid_candles=2, score=80)
    base.update(kw)
    return Signal(**base)


@pytest.mark.parametrize(
    "signal_kw, ctx_kw, fragment",
    [
        ({"tp2": 104}, {}, "R:R"),
        ({"stop": 99.5, "tp2": 102}, {}, "stop curto demais: 0.50%"),
        ({"stop": 90, "tp2": 125}, {}, "stop longo demais: 10.00%"),
        ({}, {"allow_new_entries": False, "regime": "risk_off"}, "risk_off"),
        ({}, {"spread_pct": {"XUSDT": 0.3}}, "spread"),
        ({}, {"open_symbols": {"XUSDT"}}, "posição aberta"),
        ({}, {"last_stop_ms": {"XUSDT": 1_000 * H - 5 * H}}, "stop há menos de 24 h"),
    ],
)
def test_filtros_comuns(cfg, signal_kw, ctx_kw, fragment):
    ctx = SignalContext(now_ms=1_000 * H, spread_pct={"XUSDT": 0.05})
    for k, v in ctx_kw.items():
        setattr(ctx, k, v)
    problems = check_filters(make_signal(**signal_kw), ctx, cfg.setups.common, 0.15)
    assert any(fragment in p for p in problems), problems


def test_sinal_bom_passa_e_cooldown_expira(cfg):
    ctx = SignalContext(now_ms=1_000 * H, spread_pct={"XUSDT": 0.05}, last_stop_ms={"XUSDT": 1_000 * H - 25 * H})
    assert check_filters(make_signal(), ctx, cfg.setups.common, 0.15) == []


def test_order_link_id_cabe_na_bybit():
    s = make_signal(symbol="1000000BABYDOGEUSDT", setup="rompimento_compressao")
    assert len(s.order_link_id) <= 36
    assert make_signal().order_link_id == "XUSDT-pb-202610120000"  # 1_791_763_200_000 = 12/10 00:00 UTC


def test_validade_em_velas():
    s = make_signal(valid_candles=2)
    assert s.valid_until_ms == s.candle_start_ms + 3 * H


def test_payload_do_sinal():
    p = signal_payload(make_signal())
    assert p["status"] == "pendente" and p["rr"] == 3.0
    assert set(p) == {"symbol", "setup", "entry", "stop", "tp1", "tp2", "rr", "score", "status", "reason",
                      "order_link_id"}


def test_engine_avalia_e_filtra(cfg):
    h1 = candles(path(pullback_closes()))
    ctx = SignalContext(end_ms(h1), spread_pct={"PBUSDT": 0.05})
    evals = evaluate("PBUSDT", h1, h4_for(h1), {"trend": 25, "squeeze": 0}, 80, ctx, cfg)
    assert [e.signal.setup for e in evals] == ["pullback_tendencia"]
    assert evals[0].approved


def test_closed_only():
    df = candles([(1, 1, 1, 1)] * 3)
    assert len(closed_only(df, "60", end_ms(df) - 1)) == 2
    assert len(closed_only(df, "60", end_ms(df))) == 3


# ------------------------------------------------------------------ planos de entrada (painel)
def test_planos_de_entrada_seguem_as_regras_dos_setups(cfg):
    from bot.signals.plans import entry_plans, plan_lines

    h1 = candles(path(pullback_closes()))
    plans = entry_plans(h1, h4_for(h1), {"trend": 25, "squeeze": 15}, end_ms(h1), cfg)
    assert [p.setup for p in plans] == ["pullback_tendencia", "rompimento_compressao"]
    for p in plans:
        assert p.stop < p.entry < p.tp1 < p.tp2
        assert (p.tp2 - p.entry) / (p.entry - p.stop) == pytest.approx(cfg.exits.tp2_r)
    pb = plans[0]
    assert pb.zone[0] < pb.zone[1]
    lines = plan_lines(plans, cfg.setups.common, cfg.exits)
    assert lines[0].startswith("Plano Pullback: zona de compra") and "(1,5R)" in lines[0] and "(3R)" in lines[0]
    assert lines[-1].startswith("⚠ Planos informativos")


def test_sem_plano_quando_score_nao_atende(cfg):
    from bot.signals.plans import entry_plans, plan_lines

    h1 = candles(path(pullback_closes()))
    assert entry_plans(h1, h4_for(h1), {"trend": 10, "squeeze": 2}, end_ms(h1), cfg) == []
    assert plan_lines([], cfg.setups.common, cfg.exits)[0].startswith("Plano: nenhum setup")


# ------------------------------------------------------------------ venda pelo gráfico invertido
def test_grafico_invertido():
    from bot.signals.direction import invert_frame

    df = candles([(100, 110, 90, 105)])
    inv = invert_frame(df)
    row = inv.iloc[0]
    assert row["open"] == pytest.approx(1 / 100) and row["close"] == pytest.approx(1 / 105)
    assert row["high"] == pytest.approx(1 / 90) and row["low"] == pytest.approx(1 / 110)
    assert row["high"] >= max(row["open"], row["close"]) >= min(row["open"], row["close"]) >= row["low"]


def test_queda_vira_alta_e_o_setup_encontra_a_venda(cfg):
    from bot.signals.direction import invert_frame, to_short

    # espelho do caso de pullback que dispara: preço em queda com repique e confirmação para baixo
    closes = [1 / c for c in pullback_closes()]
    h1 = candles(path(closes))
    inv = invert_frame(h1)
    long_on_inverted = run_pullback(cfg, inv)
    assert long_on_inverted is not None
    short = to_short(long_on_inverted, cfg.exits)
    assert short.direction == -1 and short.side == "Venda"
    assert short.stop > short.entry > short.tp1 > short.tp2
    assert short.risk > 0
    assert short.rr == pytest.approx(cfg.exits.tp2_r)  # alvos recalculados no preço real
    assert short.entry == pytest.approx(1 / long_on_inverted.entry)
    assert short.stop == pytest.approx(1 / long_on_inverted.stop)
    raw = to_short(long_on_inverted)  # sem exits: só converte (1/x distorce alvos distantes)
    assert raw.tp2 == pytest.approx(1 / long_on_inverted.tp2)
    assert short.order_link_id.split("-")[1] == "pbs"
    assert short.reasons[0].startswith("Venda pelo gráfico invertido")


def test_filtros_valem_para_venda(cfg):
    sell = make_signal(entry=100.0, stop=103.0, tp1=95.5, tp2=91.0, direction=-1)
    ctx = SignalContext(now_ms=1_000 * H, spread_pct={"XUSDT": 0.05})
    assert sell.rr == pytest.approx(3.0) and sell.stop_pct == pytest.approx(3.0)
    assert check_filters(sell, ctx, cfg.setups.common, 0.15) == []
    wrong = make_signal(entry=100.0, stop=97.0, tp1=95.5, tp2=91.0, direction=-1)  # stop do lado errado
    assert any("R:R" in p for p in check_filters(wrong, ctx, cfg.setups.common, 0.15))
