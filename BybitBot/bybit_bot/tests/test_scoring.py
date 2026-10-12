from __future__ import annotations

import math

import pytest

from bot.config import load_config
from bot.data.market_data import DerivativesSnapshot
from bot.scanner.features import Features
from bot.scanner.scoring import classify, score_features
from conftest import CONFIG_PATH

NAN = float("nan")


@pytest.fixture(scope="module")
def sc():
    return load_config(CONFIG_PATH).score


def perfect(**overrides) -> Features:
    """Features que cumprem TODAS as condições e nenhuma penalidade."""
    base = dict(
        symbol="TESTUSDT",
        close_4h=110, ema20_4h=105, ema50_4h=100, ema200_4h=90, adx_4h=30, plus_di_4h=30, minus_di_4h=10,
        obv_4h=1000, obv_past_4h=900, obv_ema_4h=950, cmf_4h=0.10, bb_width_rank_4h=10, range_position_4h=0.9,
        atr_4h=2, atr_avg_4h=3, rsi_4h=60, macd_hist_4h=2, macd_hist_prev_4h=1,
        close_1d=110, ema50_1d=100, daily_candles=300, ret_short=0.10, ret_long=0.20,
        btc_ret_short=0.02, btc_ret_long=0.05, ratio_btc=2.0, ratio_btc_ema=1.8,
        max_upper_wick_fraction_1d=0.2, rsi_1h=55, volume_ratio=2.0, change_24h_pct=3.0,
        derivatives=DerivativesSnapshot("TESTUSDT", 0.01, 1e6, 10.0, 1.2, 0),
    )
    base.update(overrides)
    return Features(**base)


def test_score_maximo_100_com_tudo_atendido(sc):
    r = score_features(perfect(), sc)
    assert r.components == {"trend": 25, "relative_strength": 20, "volume": 20, "squeeze": 15,
                            "derivatives": 10, "momentum": 10}
    assert r.penalties == 0
    assert r.total == 100
    assert "EMA50 4H acima da EMA200 4H (+7)" in r.reasons
    assert r.missing == []


@pytest.mark.parametrize(
    "overrides, component, lost",
    [
        ({"close_4h": 99}, "trend", 7),                                      # preço abaixo da EMA50 4H
        ({"ema50_4h": 95, "ema200_4h": 96, "close_4h": 110}, "trend", 7),     # EMA50 < EMA200
        ({"close_1d": 99}, "trend", 5),                                      # abaixo da EMA50 diária
        ({"adx_4h": 19}, "trend", 6),                                        # ADX fraco
        ({"plus_di_4h": 5}, "trend", 6),                                     # DI+ < DI−
        ({"ret_short": 0.01}, "relative_strength", 6),                       # 7d pior que o BTC
        ({"ret_long": 0.04}, "relative_strength", 6),                        # 30d pior que o BTC
        ({"ratio_btc": 1.7}, "relative_strength", 8),                        # razão abaixo da EMA
        ({"volume_ratio": 1.2}, "volume", 8),                                # volume abaixo da faixa
        ({"volume_ratio": 4.5}, "volume", 8),                                # volume acima da faixa
        ({"obv_4h": 940}, "volume", 6),                                      # OBV abaixo da média
        ({"obv_past_4h": 1001}, "volume", 6),                                # OBV caindo
        ({"cmf_4h": 0.05}, "volume", 6),                                     # CMF no limite (não >)
        ({"bb_width_rank_4h": 26}, "squeeze", 8),                            # Bandas largas
        ({"range_position_4h": 0.5}, "squeeze", 4),                          # meio do range
        ({"atr_4h": 3.5}, "squeeze", 3),                                     # ATR expandindo
        ({"rsi_4h": 49}, "momentum", 5),                                     # RSI abaixo da faixa
        ({"rsi_4h": 69}, "momentum", 5),                                     # RSI acima da faixa
        ({"macd_hist_4h": -1, "macd_hist_prev_4h": -2}, "momentum", 5),       # histograma negativo
        ({"macd_hist_4h": 1, "macd_hist_prev_4h": 2}, "momentum", 5),         # positivo mas caindo
    ],
)
def test_cada_condicao_perde_seus_pontos(sc, overrides, component, lost):
    r = score_features(perfect(**overrides), sc)
    expected = {"trend": 25, "relative_strength": 20, "volume": 20, "squeeze": 15, "derivatives": 10,
                "momentum": 10}[component] - lost
    assert r.components[component] == expected


@pytest.mark.parametrize(
    "deriv, expected",
    [
        (DerivativesSnapshot("X", 0.01, 1e6, 4.0, 1.2, 0), 6),     # OI subiu pouco
        (DerivativesSnapshot("X", 0.01, 1e6, 10.0, 1.2, 0), 10),   # tudo ok
        (DerivativesSnapshot("X", 0.04, 1e6, 10.0, 1.2, 0), 7),    # funding acima de 0,03 %
        (DerivativesSnapshot("X", -0.02, 1e6, 10.0, 1.2, 0), 7),   # funding abaixo de −0,01 %
        (DerivativesSnapshot("X", 0.01, 1e6, 10.0, 1.6, 0), 7),    # multidão comprada
        (DerivativesSnapshot("X", 0.01, None, None, 1.2, 0), 6),   # OI ausente: só não pontua
    ],
)
def test_derivativos(sc, deriv, expected):
    assert score_features(perfect(derivatives=deriv), sc).components["derivatives"] == expected


def test_oi_subindo_com_preco_esticado_nao_pontua(sc):
    r = score_features(perfect(change_24h_pct=9.0), sc)
    assert r.components["derivatives"] == 6


def test_sem_perpetuo_recebe_pontuacao_neutra(sc):
    r = score_features(perfect(derivatives=None), sc)
    assert r.components["derivatives"] == sc.derivatives_neutral_points
    assert any("Sem perpétuo listado" in x for x in r.reasons)


def test_perpetuo_sem_nenhum_dado_tambem_e_neutro(sc):
    r = score_features(perfect(derivatives=DerivativesSnapshot("X", None, None, None, None, 0)), sc)
    assert r.components["derivatives"] == sc.derivatives_neutral_points


@pytest.mark.parametrize(
    "overrides, penalty",
    [
        ({"rsi_4h": 76}, -10),                               # sobrecomprado
        ({"close_4h": 118, "ema20_4h": 105}, -10),           # 12,4 % acima da EMA20
        ({"volume_ratio": 6.5}, -8),                         # pump
        ({"max_upper_wick_fraction_1d": 0.65}, -5),          # pavio de rejeição
    ],
)
def test_penalidades(sc, overrides, penalty):
    r = score_features(perfect(**overrides), sc)
    assert r.penalties == penalty


def test_funding_superaquecido_penaliza(sc):
    r = score_features(perfect(derivatives=DerivativesSnapshot("X", 0.06, 1e6, 10.0, 1.2, 0)), sc)
    assert r.penalties == -5
    assert r.components["derivatives"] == 7  # e também perde o "funding ok"


def test_total_fica_entre_0_e_100(sc):
    awful = perfect(close_4h=50, ema20_4h=100, ema50_4h=100, ema200_4h=120, close_1d=50, adx_4h=5,
                    ret_short=-0.5, ret_long=-0.5, ratio_btc=1, volume_ratio=7, obv_4h=0, cmf_4h=-1,
                    bb_width_rank_4h=99, range_position_4h=0, atr_4h=5, rsi_4h=80, macd_hist_4h=-1,
                    max_upper_wick_fraction_1d=0.9, derivatives=DerivativesSnapshot("X", 0.1, 1, -5, 3, 0))
    r = score_features(awful, sc)
    assert r.raw < 0
    assert r.total == 0


def test_dado_ausente_nao_pontua_e_e_registrado(sc):
    r = score_features(perfect(ema200_4h=NAN, bb_width_rank_4h=NAN), sc)
    assert r.components["trend"] == 18
    assert r.components["squeeze"] == 7
    assert len(r.missing) == 2


def test_features_vazias_nao_quebram(sc):
    r = score_features(Features("VAZIOUSDT"), sc)
    assert r.total == sc.derivatives_neutral_points  # só a pontuação neutra de derivativos
    assert not math.isnan(r.total)


@pytest.mark.parametrize(
    "total, regime, expected",
    [(70, "risk_on", "A"), (69.9, "risk_on", "B"), (60, "risk_on", "B"), (59, "risk_on", "-"),
     (72, "neutro", "B"), (75, "neutro", "A"), (80, "risk_off", "A")],
)
def test_classificacao(sc, total, regime, expected):
    assert classify(total, sc, regime) == expected
