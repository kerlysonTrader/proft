"""Setup 1 — pullback_tendencia (1H), seção 4 do 03_ESTRATEGIA.md.

1. Componente de tendência do score >= min_trend_points.
2. Nas últimas `pullback_lookback_1h` velas 1H, alguma recuou até a zona entre a EMA20 e a
   EMA50 1H (mínima <= EMA20 sem fechar abaixo da EMA50) ou tocou a EMA20 4H.
3. O RSI 1H desceu até a faixa 35–45 (sem furar 35) e voltou acima de 45.
4. A última vela 1H FECHADA confirma: fecha acima da EMA20 1H, corpo >= 50 % do range e
   fecha acima da máxima anterior (ou engolfo de alta).
Entrada: limite no fechamento da confirmação + tolerância; stop: mínima do pullback − buffer × ATR.
Alvos em múltiplos de R (exits.tp1_r / exits.tp2_r).
"""

from __future__ import annotations

import pandas as pd

from bot.bybit.client import KLINE_INTERVAL_MS
from bot.indicators import atr, ema, rsi
from bot.signals.base import TF_LABEL, Signal, body_fraction, closed_only, is_bullish_engulfing


def pullback_signal(symbol: str, h1: pd.DataFrame, h4: pd.DataFrame, now_ms: int, trend_points: float,
                    score: float, cfg, ind, exits, trigger: str = "60", context: str = "240") -> Signal | None:
    """cfg = setups.pullback_tendencia, ind = indicators, exits = exits.

    h1/h4 = velas do tempo gráfico do gatilho e do contexto (padrão 1H/4H; intraday 15m/1H).
    """
    if trend_points < cfg.min_trend_points:
        return None
    h1 = closed_only(h1, trigger, now_ms)
    h4 = closed_only(h4, context, now_ms)
    tf, ctf = TF_LABEL[trigger], TF_LABEL[context]
    lookback = cfg.pullback_lookback_1h
    if len(h1) < max(ind.ema_mid, ind.rsi_period) + lookback + 2:
        return None

    close = h1["close"]
    ema20 = ema(close, ind.ema_short)
    ema50 = ema(close, ind.ema_mid)
    rsi1 = rsi(close, ind.rsi_period)
    atr1 = atr(h1, ind.atr_period)
    ema20_4h = ema(h4["close"], ind.ema_short).iloc[-1] if len(h4) >= ind.ema_short else float("nan")

    window = h1.iloc[-lookback - 1:-1]  # o recuo acontece ANTES da vela de confirmação
    w_ema20, w_ema50 = ema20.loc[window.index], ema50.loc[window.index]
    in_zone = ((window["low"] <= w_ema20) & (window["close"] >= w_ema50)).any()
    touched_4h = bool((window["low"] <= ema20_4h).any()) if not pd.isna(ema20_4h) else False
    if not (in_zone or touched_4h):
        return None

    band_low, band_high = cfg.rsi_touch_band_1h
    rsi_min = rsi1.loc[window.index].min()
    current_rsi = rsi1.iloc[-1]
    if pd.isna(rsi_min) or not (band_low <= rsi_min <= band_high) or not current_rsi > band_high:
        return None

    cur, prev = h1.iloc[-1], h1.iloc[-2]
    confirms = (cur["close"] > ema20.iloc[-1] and body_fraction(cur) >= cfg.min_body_fraction
                and (cur["close"] > prev["high"] or is_bullish_engulfing(prev, cur)))
    if not confirms:
        return None

    atr_now = atr1.iloc[-1]
    entry = float(cur["close"]) * (1 + cfg.entry_tolerance_pct / 100)
    pullback_low = float(h1["low"].iloc[-lookback - 1:].min())
    stop = pullback_low - cfg.stop_atr_buffer * float(atr_now)
    risk = entry - stop
    if pd.isna(atr_now) or risk <= 0:
        return None
    zone = f"zona EMA20–EMA50 {tf}" if in_zone else f"EMA20 {ctf}"
    return Signal(
        symbol=symbol, setup="pullback_tendencia", entry=entry, stop=stop,
        tp1=entry + exits.tp1_r * risk, tp2=entry + exits.tp2_r * risk,
        candle_start_ms=int(cur["start_ms"]), valid_candles=cfg.order_valid_candles_1h, score=score,
        reasons=(f"Tendência {trend_points:g} pts (mín. {cfg.min_trend_points:g})",
                 f"Recuo até a {zone}",
                 f"RSI {tf} desceu a {rsi_min:.0f} e voltou a {current_rsi:.0f}",
                 f"Vela {tf} de confirmação: fechou acima da EMA20 {tf} com corpo forte"
                 + (" (engolfo de alta)" if is_bullish_engulfing(prev, cur) else " e acima da máxima anterior"),
                 f"Stop na mínima do pullback − {cfg.stop_atr_buffer:g} × ATR {tf}"),
        interval_ms=KLINE_INTERVAL_MS[trigger],
    )
