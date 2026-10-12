"""Indicadores técnicos — funções puras sobre pandas, sem olhar o futuro.

Convenções (iguais ao TradingView, para conferência do Gate 2):
- EMA: alfa = 2/(n+1), semeada com a média simples das n primeiras velas (TA-Lib/TradingView
  convergem para o mesmo valor depois do aquecimento; use >= 3-5x o período de histórico).
- RMA (Wilder, usada em RSI, ATR e ADX): alfa = 1/n, semeada com a média simples.
- Desvio padrão das Bandas de Bollinger: populacional (ddof=0), como o ta.stdev do TradingView.
- Valor de cada vela usa apenas aquela vela e as anteriores. Fractais são publicados na vela
  em que ficam CONFIRMADOS (n velas depois do topo/fundo), nunca na própria vela do pivô.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _check_period(period: int) -> None:
    if period < 1:
        raise ValueError("período deve ser >= 1")


def sma(series: pd.Series, period: int) -> pd.Series:
    _check_period(period)
    return series.rolling(period, min_periods=period).mean()


def _seeded_recursive(series: pd.Series, period: int, alpha: float) -> pd.Series:
    """Média exponencial semeada com a SMA das primeiras `period` observações válidas."""
    _check_period(period)
    values = series.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    # semente: primeiras `period` observações válidas CONSECUTIVAS
    run, seed_end = 0, None
    for i, value in enumerate(values):
        run = 0 if np.isnan(value) else run + 1
        if run == period:
            seed_end = i
            break
    if seed_end is None:
        return pd.Series(out, index=series.index)
    prev = values[seed_end - period + 1:seed_end + 1].mean()
    out[seed_end] = prev
    for i in range(seed_end + 1, len(values)):
        value = values[i]
        if not np.isnan(value):
            prev = alpha * value + (1 - alpha) * prev
        out[i] = prev
    return pd.Series(out, index=series.index)


def ema(series: pd.Series, period: int) -> pd.Series:
    return _seeded_recursive(series, period, 2 / (period + 1))


def rma(series: pd.Series, period: int) -> pd.Series:
    """Média de Wilder (RMA/SMMA)."""
    return _seeded_recursive(series, period, 1 / period)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI de Wilder (0–100)."""
    change = close.diff()
    gain = change.clip(lower=0)
    loss = (-change).clip(lower=0)
    avg_gain = rma(gain, period)
    avg_loss = rma(loss, period)
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    out = out.where(avg_loss != 0, 100.0)                      # só altas
    out = out.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)  # sem variação
    return out.where(avg_gain.notna())


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1)
    tr = ranges.max(axis=1, skipna=True)
    tr.iloc[:1] = (df["high"] - df["low"]).iloc[:1]  # primeira vela: máxima − mínima
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR de Wilder."""
    return rma(true_range(df), period)


def dmi(df: pd.DataFrame, period: int = 14, adx_smoothing: int | None = None) -> pd.DataFrame:
    """DI+, DI− e ADX (Wilder), como o ta.dmi do TradingView. Colunas: plus_di, minus_di, adx."""
    adx_smoothing = adx_smoothing or period
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index).where(up.notna())
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index).where(down.notna())
    tr_rma = rma(true_range(df).where(up.notna()), period)
    plus_di = 100 * rma(plus_dm, period) / tr_rma
    minus_di = 100 * rma(minus_dm, period) / tr_rma
    total = (plus_di + minus_di).replace(0, 1)
    adx = 100 * rma((plus_di - minus_di).abs() / total, adx_smoothing)
    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": adx})


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Colunas: macd, signal, hist."""
    if fast >= slow:
        raise ValueError("fast deve ser menor que slow")
    line = ema(close, fast) - ema(close, slow)
    signal_line = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": signal_line, "hist": line - signal_line})


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Colunas: basis, upper, lower, width (= (upper − lower) / basis)."""
    basis = sma(close, period)
    dev = close.rolling(period, min_periods=period).std(ddof=0)
    upper = basis + num_std * dev
    lower = basis - num_std * dev
    return pd.DataFrame({"basis": basis, "upper": upper, "lower": lower, "width": (upper - lower) / basis})


def percentile_rank(series: pd.Series, lookback: int) -> pd.Series:
    """% dos valores da janela (inclui o atual) que são <= ao valor atual. 0–100."""
    if lookback < 2:
        raise ValueError("lookback deve ser >= 2")

    def _rank(window: np.ndarray) -> float:
        return float((window <= window[-1]).sum()) / len(window) * 100

    return series.rolling(lookback, min_periods=lookback).apply(_rank, raw=True)


def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume, começando em 0 na primeira vela."""
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Chaikin Money Flow."""
    _check_period(period)
    span = df["high"] - df["low"]
    multiplier = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / span.replace(0, np.nan)
    money_flow_volume = multiplier.fillna(0) * df["volume"]
    volume_sum = df["volume"].rolling(period, min_periods=period).sum()
    return money_flow_volume.rolling(period, min_periods=period).sum() / volume_sum.replace(0, np.nan)


def fractals(df: pd.DataFrame, bars: int = 5) -> pd.DataFrame:
    """Fractais de Williams (topo/fundo com `bars` velas de cada lado, estritamente maior/menor).

    Publicados na vela de CONFIRMAÇÃO (pivô + `bars`), sem olhar o futuro. Colunas:
    fractal_high / fractal_low = preço do pivô; *_pos = posição (iloc) da vela do pivô.
    """
    _check_period(bars)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    n = len(df)
    fh = np.full(n, np.nan)
    fl = np.full(n, np.nan)
    fh_pos = np.full(n, np.nan)
    fl_pos = np.full(n, np.nan)
    for pivot in range(bars, n - bars):
        confirm = pivot + bars
        left_h, right_h = high[pivot - bars:pivot], high[pivot + 1:confirm + 1]
        if high[pivot] > left_h.max() and high[pivot] > right_h.max():
            fh[confirm], fh_pos[confirm] = high[pivot], pivot
        left_l, right_l = low[pivot - bars:pivot], low[pivot + 1:confirm + 1]
        if low[pivot] < left_l.min() and low[pivot] < right_l.min():
            fl[confirm], fl_pos[confirm] = low[pivot], pivot
    return pd.DataFrame(
        {"fractal_high": fh, "fractal_high_pos": fh_pos, "fractal_low": fl, "fractal_low_pos": fl_pos},
        index=df.index)
