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
    no_benchmark: bool = False      # sem ativo de referência (forex/metais/energia): força relativa neutra

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
    values: dict[str, float | int | DerivativesSnapshot | None] = {"symbol": symbol, "derivatives": derivatives,
                                                                    "no_benchmark": len(btc_d1) == 0}

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


FEATURE_COLUMNS = [name for name in Features.__dataclass_fields__ if name not in ("symbol", "derivatives")]


def _ends(df: pd.DataFrame, interval_ms: int) -> pd.Index:
    return pd.Index(df["start_ms"].to_numpy() + interval_ms)


def feature_frame(d1: pd.DataFrame, h4: pd.DataFrame, h1: pd.DataFrame, btc_d1: pd.DataFrame, ind, sc
                  ) -> pd.DataFrame:
    """As mesmas features de compute_features, para TODAS as horas de uma vez (backtest).

    Índice = fechamento de cada vela 1H (ms). Cada linha usa só velas 1H/4H/1D já fechadas naquele
    instante. Válido porque todos os indicadores são causais (tests/test_indicators.py).
    """
    hour_ends = _ends(h1, 3_600_000)
    out = pd.DataFrame(index=hour_ends)

    if len(h4):
        c4 = h4["close"]
        d = dmi(h4, ind.adx_period)
        o = obv(h4)
        hist = macd(c4, ind.macd_fast, ind.macd_slow, ind.macd_signal)["hist"]
        atr4 = atr(h4, ind.atr_period)
        lo = h4["low"].rolling(sc.range_lookback_4h, min_periods=1).min()
        hi = h4["high"].rolling(sc.range_lookback_4h, min_periods=1).max()
        f4 = pd.DataFrame({
            "close_4h": c4,
            "ema20_4h": ema(c4, ind.ema_short),
            "ema50_4h": ema(c4, ind.ema_mid),
            "ema200_4h": ema(c4, ind.ema_long),
            "adx_4h": d["adx"], "plus_di_4h": d["plus_di"], "minus_di_4h": d["minus_di"],
            "obv_4h": o, "obv_past_4h": o.shift(sc.obv_slope_bars), "obv_ema_4h": ema(o, ind.obv_ema_period),
            "cmf_4h": cmf(h4, ind.cmf_period),
            "bb_width_rank_4h": percentile_rank(bollinger(c4, ind.bollinger_period, ind.bollinger_std)["width"],
                                                ind.bb_width_lookback),
            "range_position_4h": ((c4 - lo) / (hi - lo)).where(hi > lo),
            "atr_4h": atr4, "atr_avg_4h": sma(atr4, ind.atr_avg_period),
            "rsi_4h": rsi(c4, ind.rsi_period),
            "macd_hist_4h": hist, "macd_hist_prev_4h": hist.shift(1),
        })
        f4.index = _ends(h4, 4 * 3_600_000)
        out = out.join(f4.reindex(hour_ends, method="ffill"))

    if len(d1):
        cd = d1["close"]
        span = d1["high"] - d1["low"]
        wick = (d1["high"] - d1[["open", "close"]].max(axis=1)) / span.where(span > 0)
        f1 = pd.DataFrame({
            "close_1d": cd,
            "ema50_1d": ema(cd, ind.ema_mid),
            "daily_candles": pd.Series(range(1, len(d1) + 1), index=d1.index),
            "ret_short": cd / cd.shift(sc.rs_short_days) - 1,
            "ret_long": cd / cd.shift(sc.rs_long_days) - 1,
            "max_upper_wick_fraction_1d": wick.rolling(sc.wick_lookback_days, min_periods=1).max(),
            "avg_daily_turnover": d1["turnover"].shift(1).rolling(ind.volume_avg_period).mean(),
        })
        if len(btc_d1):
            cb = btc_d1["close"]
            ratio = (cd / cb.reindex(cd.index)).dropna()
            f1 = f1.join(pd.DataFrame({"ratio_btc": ratio, "ratio_btc_ema": ema(ratio, sc.ratio_ema_period)}))
        f1.index = _ends(d1, 86_400_000)
        out = out.join(f1.reindex(hour_ends, method="ffill"))
        out["daily_candles"] = out["daily_candles"].fillna(0).astype(int)

    if len(btc_d1):
        cb = btc_d1["close"]
        fb = pd.DataFrame({"btc_ret_short": cb / cb.shift(sc.rs_short_days) - 1,
                           "btc_ret_long": cb / cb.shift(sc.rs_long_days) - 1})
        fb.index = _ends(btc_d1, 86_400_000)
        out = out.join(fb.reindex(hour_ends, method="ffill"))

    c1 = h1["close"]
    out["rsi_1h"] = rsi(c1, ind.rsi_period).to_numpy()
    out["change_24h_pct"] = ((c1 / c1.shift(HOURS_24) - 1) * 100).to_numpy()
    turnover_24h = h1["turnover"].rolling(HOURS_24).sum().to_numpy()
    if "avg_daily_turnover" in out:
        out["volume_ratio"] = turnover_24h / out["avg_daily_turnover"].where(out["avg_daily_turnover"] > 0)
        out["turnover_24h"] = turnover_24h
        out = out.drop(columns=["avg_daily_turnover"])
    out["no_benchmark"] = 0.0 if len(btc_d1) else 1.0
    for column in FEATURE_COLUMNS:
        if column not in out:
            out[column] = 0 if column == "daily_candles" else NAN
    return out


def features_from_row(symbol: str, row: pd.Series, derivatives: DerivativesSnapshot | None = None) -> Features:
    values = {k: (int(row[k]) if k == "daily_candles" else bool(row[k]) if k == "no_benchmark" else float(row[k]))
              for k in FEATURE_COLUMNS}
    return Features(symbol=symbol, derivatives=derivatives, **values)


def is_num(value: float | None) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))
