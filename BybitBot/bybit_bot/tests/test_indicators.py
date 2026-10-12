from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from bot.indicators import atr, bollinger, cmf, dmi, ema, fractals, macd, obv, percentile_rank, rma, rsi, sma


def ohlcv(rows: list[tuple[float, float, float, float]], start: str = "2026-01-01") -> pd.DataFrame:
    """rows = (high, low, close, volume); open = close anterior."""
    df = pd.DataFrame(rows, columns=["high", "low", "close", "volume"],
                      index=pd.date_range(start, periods=len(rows), freq="h", tz="UTC"))
    df.insert(0, "open", df["close"].shift(1).fillna(df["close"]))
    return df


def random_walk(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    spread = np.abs(rng.normal(0, 0.006, n)) * close
    high = close + spread * rng.uniform(0.2, 1, n)
    low = close - spread * rng.uniform(0.2, 1, n)
    volume = rng.uniform(100, 1000, n)
    return ohlcv(list(zip(high, low, close, volume, strict=True)))


def assert_series(actual: pd.Series, expected: list[float], tol: float = 1e-9) -> None:
    assert len(actual) == len(expected)
    for got, want in zip(actual.tolist(), expected, strict=True):
        if want is None or (isinstance(want, float) and math.isnan(want)):
            assert math.isnan(got), f"esperado NaN, veio {got}"
        else:
            assert got == pytest.approx(want, abs=tol), f"{got} != {want}"


NAN = float("nan")


# ---------------------------------------------------------------- valores calculados à mão
def test_sma_e_ema_a_mao():
    s = pd.Series([1, 2, 3, 4, 5, 6], dtype=float)
    assert_series(sma(s, 3), [NAN, NAN, 2, 3, 4, 5])
    # semente = SMA(1,2,3) = 2; alfa = 0,5 -> 3, 4, 5
    assert_series(ema(s, 3), [NAN, NAN, 2, 3, 4, 5])


def test_rma_wilder_a_mao():
    s = pd.Series([3, 6, 9, 12], dtype=float)
    # semente = 6; depois 12/3 + 6*2/3 = 8
    assert_series(rma(s, 3), [NAN, NAN, 6, 8])


def test_rsi_exemplo_classico_de_wilder():
    # série clássica do RSI (StockCharts); valores conferidos à mão:
    # 1º: ganhos 3,34/14 e perdas 1,40/14 -> RSI = 100 - 100/(1 + 3,34/1,40) = 70,464
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61,
              46.28, 46.28, 46.00, 46.03]
    values = rsi(pd.Series(closes), 14)
    assert values.iloc[:14].isna().all()
    assert values.iloc[14] == pytest.approx(70.464, abs=0.01)
    assert values.iloc[15] == pytest.approx(66.250, abs=0.01)  # variação −0,28
    assert values.iloc[16] == pytest.approx(66.481, abs=0.02)  # variação +0,03


def test_rsi_extremos():
    up = pd.Series(np.arange(1, 30, dtype=float))
    assert rsi(up, 14).iloc[-1] == 100
    flat = pd.Series([5.0] * 30)
    assert rsi(flat, 14).iloc[-1] == 50


def test_true_range_e_atr_a_mao():
    df = ohlcv([(10, 8, 9, 1), (11, 9, 10, 1), (12, 9.5, 11, 1), (15, 11, 14, 1)])
    # TR = 2, 2, 2.5, 4 ; ATR(3): semente 6.5/3 ; depois (2.1667*2 + 4)/3
    assert_series(atr(df, 3), [NAN, NAN, 6.5 / 3, (6.5 / 3 * 2 + 4) / 3])


def test_bollinger_a_mao():
    bb = bollinger(pd.Series([1, 2, 3, 4, 5], dtype=float), 5, 2)
    std = math.sqrt(2)  # desvio populacional de 1..5
    assert bb["basis"].iloc[-1] == pytest.approx(3)
    assert bb["upper"].iloc[-1] == pytest.approx(3 + 2 * std)
    assert bb["lower"].iloc[-1] == pytest.approx(3 - 2 * std)
    assert bb["width"].iloc[-1] == pytest.approx(4 * std / 3)


def test_percentile_rank_a_mao():
    pr = percentile_rank(pd.Series([1, 3, 2, 5, 4], dtype=float), 3)
    assert_series(pr, [NAN, NAN, 200 / 3, 100, 200 / 3])


def test_obv_a_mao():
    df = ohlcv([(11, 9, 10, 100), (12, 10, 11, 200), (11, 10, 10.5, 150), (11, 10, 10.5, 120),
                (13, 11, 12, 300)])
    assert_series(obv(df), [0, 200, 50, 50, 350])


def test_cmf_a_mao():
    df = ohlcv([(10, 8, 9, 100), (12, 10, 12, 200), (12, 10, 10, 100)])
    # multiplicadores 0, +1, −1 -> fluxos 0, 200, −100
    assert_series(cmf(df, 2), [NAN, 200 / 300, 100 / 300])


def test_cmf_vela_sem_amplitude_nao_quebra():
    df = ohlcv([(10, 10, 10, 100), (10, 10, 10, 100)])
    assert cmf(df, 2).iloc[-1] == 0


def test_macd_consistente():
    close = random_walk()["close"]
    m = macd(close, 12, 26, 9)
    assert_series(m["macd"], (ema(close, 12) - ema(close, 26)).tolist())
    assert_series(m["hist"], (m["macd"] - m["signal"]).tolist())
    assert m["macd"].first_valid_index() == close.index[25]
    assert m["signal"].first_valid_index() == close.index[25 + 8]


def test_fractais_publicados_na_vela_de_confirmacao():
    highs = [1, 2, 3, 2, 1, 2, 2.5, 2, 1, 1]
    lows = [h - 0.5 for h in highs]
    lows[8] = -1  # fundo no índice 8 não confirma (faltam velas depois)
    df = ohlcv([(h, lo, h - 0.2, 1) for h, lo in zip(highs, lows, strict=True)])
    f = fractals(df, 2)
    assert f["fractal_high"].iloc[4] == 3 and f["fractal_high_pos"].iloc[4] == 2
    assert f["fractal_high"].iloc[:4].isna().all()           # nada antes da confirmação
    assert f["fractal_high"].iloc[8] == 2.5 and f["fractal_high_pos"].iloc[8] == 6
    assert f["fractal_low"].isna().all() or f["fractal_low"].dropna().index.max() < df.index[8]


def test_fractal_exige_maximo_estrito():
    df = ohlcv([(1, 0, 0.5, 1), (3, 2, 2.5, 1), (3, 2, 2.5, 1), (1, 0, 0.5, 1), (1, 0, 0.5, 1)])
    assert fractals(df, 1)["fractal_high"].isna().all()  # dois topos iguais: nenhum é fractal


# ---------------------------------------------------------------- referência em laço ("planilha")
def reference_seeded(values: list[float], period: int, alpha: float) -> list[float]:
    """Laço original (antes da otimização com ewm): semente SMA, NaN repete o anterior."""
    out = [NAN] * len(values)
    run, seed_end = 0, None
    for i, v in enumerate(values):
        run = 0 if math.isnan(v) else run + 1
        if run == period:
            seed_end = i
            break
    if seed_end is None:
        return out
    prev = sum(values[seed_end - period + 1:seed_end + 1]) / period
    out[seed_end] = prev
    for i in range(seed_end + 1, len(values)):
        if not math.isnan(values[i]):
            prev = alpha * values[i] + (1 - alpha) * prev
        out[i] = prev
    return out


@pytest.mark.parametrize("period", [1, 3, 14, 50])
def test_ema_rma_iguais_ao_laco_original_inclusive_com_buracos(period):
    rng = np.random.default_rng(period)
    values = list(100 + np.cumsum(rng.normal(0, 1, 400)))
    for i in (0, 1, 5, 6, 120, 121, 122, 300):  # buracos no início e no meio
        values[i] = NAN
    s = pd.Series(values)
    assert_series(ema(s, period), reference_seeded(values, period, 2 / (period + 1)), tol=1e-9)
    assert_series(rma(s, period), reference_seeded(values, period, 1 / period), tol=1e-9)
    short = pd.Series(values[:period - 1] if period > 1 else [])
    assert ema(short, period).isna().all()



def reference_rsi(closes: list[float], n: int) -> list[float]:
    out = [NAN] * len(closes)
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    avg_g, avg_l = sum(gains[:n]) / n, sum(losses[:n]) / n
    out[n] = 100 - 100 / (1 + avg_g / avg_l)
    for i in range(n, len(gains)):
        avg_g = (avg_g * (n - 1) + gains[i]) / n
        avg_l = (avg_l * (n - 1) + losses[i]) / n
        out[i + 1] = 100 - 100 / (1 + avg_g / avg_l)
    return out


def reference_dmi(h: list[float], lo: list[float], c: list[float], n: int) -> tuple[list, list, list]:
    """ta.dmi do TradingView reescrito com laços."""
    size = len(h)

    def wilder(values: list[float], start: int) -> list[float]:
        out = [NAN] * size
        if start + n > size:
            return out
        acc = sum(values[start:start + n]) / n
        out[start + n - 1] = acc
        for i in range(start + n, size):
            acc = (acc * (n - 1) + values[i]) / n
            out[i] = acc
        return out

    pdm, mdm, tr = [NAN] * size, [NAN] * size, [NAN] * size
    for i in range(1, size):
        up, down = h[i] - h[i - 1], lo[i - 1] - lo[i]
        pdm[i] = up if up > down and up > 0 else 0.0
        mdm[i] = down if down > up and down > 0 else 0.0
        tr[i] = max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
    tr_s, p_s, m_s = wilder(tr, 1), wilder(pdm, 1), wilder(mdm, 1)
    plus = [100 * p / t if not math.isnan(t) else NAN for p, t in zip(p_s, tr_s, strict=True)]
    minus = [100 * m / t if not math.isnan(t) else NAN for m, t in zip(m_s, tr_s, strict=True)]
    dx = [abs(p - m) / ((p + m) or 1) if not math.isnan(p) else NAN for p, m in zip(plus, minus, strict=True)]
    first = next(i for i, v in enumerate(dx) if not math.isnan(v))
    adx = [100 * v if not math.isnan(v) else NAN for v in wilder(dx, first)]
    return plus, minus, adx


def test_rsi_igual_a_referencia_em_laco():
    close = random_walk()["close"]
    assert_series(rsi(close, 14), reference_rsi(close.tolist(), 14), tol=1e-9)


def test_dmi_igual_a_referencia_em_laco():
    df = random_walk()
    plus, minus, adx = reference_dmi(df["high"].tolist(), df["low"].tolist(), df["close"].tolist(), 14)
    d = dmi(df, 14)
    assert_series(d["plus_di"], plus, tol=1e-9)
    assert_series(d["minus_di"], minus, tol=1e-9)
    assert_series(d["adx"], adx, tol=1e-9)


def test_dmi_tendencia_de_alta():
    df = ohlcv([(100 + i + 1, 100 + i - 1, 100 + i, 1) for i in range(60)])
    d = dmi(df, 14).iloc[-1]
    assert d["plus_di"] > d["minus_di"]
    assert d["adx"] > 50


# ---------------------------------------------------------------- sem olhar o futuro
INDICATORS = {
    "sma": lambda df: sma(df["close"], 20),
    "ema": lambda df: ema(df["close"], 50),
    "rsi": lambda df: rsi(df["close"], 14),
    "atr": lambda df: atr(df, 14),
    "dmi": lambda df: dmi(df, 14),
    "macd": lambda df: macd(df["close"]),
    "bollinger": lambda df: bollinger(df["close"]),
    "percentile": lambda df: percentile_rank(bollinger(df["close"])["width"], 120),
    "obv": obv,
    "cmf": lambda df: cmf(df, 20),
    "fractals": lambda df: fractals(df, 5),
}


def leaks_future(fn, df: pd.DataFrame, checkpoints=(30, 80, 150, 199, 260, 299)) -> bool:
    full = fn(df)
    for t in checkpoints:
        partial = fn(df.iloc[: t + 1])
        a = np.asarray(full.iloc[t], dtype=float).ravel()
        b = np.asarray(partial.iloc[-1], dtype=float).ravel()
        if not np.allclose(a, b, equal_nan=True, rtol=0, atol=1e-9):
            return True
    return False


@pytest.mark.parametrize("name", sorted(INDICATORS))
def test_nenhum_indicador_usa_dados_futuros(name):
    assert not leaks_future(INDICATORS[name], random_walk())


def test_controle_negativo_detecta_vazamento():
    centered = lambda df: df["close"].rolling(5, center=True).mean()  # noqa: E731 — usa velas futuras
    assert leaks_future(centered, random_walk())
