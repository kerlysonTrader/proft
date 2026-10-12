"""Features de cada moeda para o score, calculadas só com velas FECHADAS.

Separar "calcular números" (aqui) de "dar pontos" (scoring.py) deixa o score testável
com valores exatos e garante que o backtest use exatamente a mesma conta.
NaN = dado insuficiente; a condição correspondente não pontua.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from bot.data.market_data import DerivativesSnapshot
from bot.indicators import atr, bollinger, cmf, dmi, ema, macd, obv, percentile_rank, rsi, sma

NAN = float("nan")
HOURS_24 = 24


@dataclass(frozen=True)
class Features:
    symbol: str
    # 4H
    close_4h: float = NAN
    ema20_4h: float = NAN
    ema50_4h: float = NAN
    ema200_4h: float = NAN
    adx_4h: float = NAN
    plus_di_4h: float = NAN
    minus_di_4h: float = NAN
    obv_4h: float = NAN
    obv_past_4h: float = NAN
    obv_ema_4h: float = NAN
    cmf_4h: float = NAN
    bb_width_rank_4h: float = NAN   # percentil 0–100 da largura das Bandas
    range_position_4h: float = NAN  # 0 = mínima, 1 = máxima do range recente
    atr_4h: float = NAN
    atr_avg_4h: float = NAN
    rsi_4h: float = NAN
    macd_hist_4h: float = NAN
    macd_hist_prev_4h: float = NAN
    # 1D
    close_1d: float = NAN
    ema50_1d: float = NAN
    daily_candles: int = 0
    ret_short: float = NAN
    ret_long: float = NAN
    btc_ret_short: float = NAN
    btc_ret_long: float = NAN
    ratio_btc: float = NAN
    ratio_btc_ema: float = NAN
    max_upper_wick_fraction_1d: float = NAN
    # 1H / 24h
    rsi_1h: float = NAN
    volume_ratio: float = NAN       # giro das últimas 24 h ÷ média diária
    change_24h_pct: float = NAN
    # derivativos (None = sem perpétuo)
    derivatives: DerivativesSnapshot | None = None

    @property
    def atr_pct_4h(self) -> float:
        return self.atr_4h / self.close_4h * 100 if self.close_4h else NAN


def _last(series: pd.Series, back: int = 0) -> float:
    if len(series) <= back:
        return NAN
    value = series.iloc[-1 - back]
    return float(value) if value is not None and not pd.isna(value) else NAN


def period_return(close: pd.Series, periods: int) -> float:
    """Retorno simples de `periods` velas atrás até a última (fração)."""
    if len(close) <= periods:
        return NAN
    past = close.iloc[-1 - periods]
    return float(close.iloc[-1] / past - 1) if past else NAN


def compute_features(
    symbol: str,
    d1: pd.DataFrame,
    h4: pd.DataFrame,
    h1: pd.DataFrame,
    btc_d1: pd.DataFrame,
    derivatives: DerivativesSnapshot | None,
    ind,   # IndicatorsConfig
    sc,    # ScoreConfig
) -> Features:
    values: dict[str, float | int | DerivativesSnapshot | None] = {"symbol": symbol, "derivatives": derivatives}

    if len(h4):
        c4 = h4["close"]
        d = dmi(h4, ind.adx_period)
        o = obv(h4)
        hist = macd(c4, ind.macd_fast, ind.macd_slow, ind.macd_signal)["hist"]
        width_rank = percentile_rank(bollinger(c4, ind.bollinger_period, ind.bollinger_std)["width"],
                                     ind.bb_width_lookback)
        atr4 = atr(h4, ind.atr_period)
        window = h4.iloc[-sc.range_lookback_4h:]
        lo, hi = window["low"].min(), window["high"].max()
        values.update(
            close_4h=_last(c4),
            ema20_4h=_last(ema(c4, ind.ema_short)),
            ema50_4h=_last(ema(c4, ind.ema_mid)),
            ema200_4h=_last(ema(c4, ind.ema_long)),
            adx_4h=_last(d["adx"]),
            plus_di_4h=_last(d["plus_di"]),
            minus_di_4h=_last(d["minus_di"]),
            obv_4h=_last(o),
            obv_past_4h=_last(o, sc.obv_slope_bars),
            obv_ema_4h=_last(ema(o, ind.obv_ema_period)),
            cmf_4h=_last(cmf(h4, ind.cmf_period)),
            bb_width_rank_4h=_last(width_rank),
            range_position_4h=float((c4.iloc[-1] - lo) / (hi - lo)) if hi > lo else NAN,
            atr_4h=_last(atr4),
            atr_avg_4h=_last(sma(atr4, ind.atr_avg_period)),
            rsi_4h=_last(rsi(c4, ind.rsi_period)),
            macd_hist_4h=_last(hist),
            macd_hist_prev_4h=_last(hist, 1),
        )

    if len(d1):
        cd = d1["close"]
        recent = d1.iloc[-sc.wick_lookback_days:]
        span = recent["high"] - recent["low"]
        upper_wick = recent["high"] - recent[["open", "close"]].max(axis=1)
        wick_frac = (upper_wick / span.where(span > 0)).max()
        values.update(
            close_1d=_last(cd),
            ema50_1d=_last(ema(cd, ind.ema_mid)),
            daily_candles=len(d1),
            ret_short=period_return(cd, sc.rs_short_days),
            ret_long=period_return(cd, sc.rs_long_days),
            max_upper_wick_fraction_1d=float(wick_frac) if not pd.isna(wick_frac) else NAN,
        )
        # volume 24h (soma das últimas 24 velas 1H) ÷ média diária das `volume_avg_period` velas anteriores
        if len(h1) >= HOURS_24 and len(d1) > ind.volume_avg_period:
            last24 = h1["turnover"].iloc[-HOURS_24:].sum()
            avg_daily = d1["turnover"].iloc[-1 - ind.volume_avg_period:-1].mean()
            values["volume_ratio"] = float(last24 / avg_daily) if avg_daily > 0 else NAN

    if len(btc_d1):
        cb = btc_d1["close"]
        values.update(btc_ret_short=period_return(cb, sc.rs_short_days),
                      btc_ret_long=period_return(cb, sc.rs_long_days))
        if len(d1):
            joined = pd.concat([d1["close"].rename("coin"), cb.rename("btc")], axis=1, join="inner")
            ratio = joined["coin"] / joined["btc"]
            values.update(ratio_btc=_last(ratio), ratio_btc_ema=_last(ema(ratio, sc.ratio_ema_period)))

    if len(h1):
        c1 = h1["close"]
        values["rsi_1h"] = _last(rsi(c1, ind.rsi_period))
        values["change_24h_pct"] = period_return(c1, HOURS_24) * 100

    return Features(**values)


def is_num(value: float | None) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))
