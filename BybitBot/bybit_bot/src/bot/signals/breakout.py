"""Setup 2 — rompimento_compressao (1H), seção 4 do 03_ESTRATEGIA.md.

1. Componente de compressão do score >= min_squeeze_points.
2. A última vela 1H FECHADA fecha acima da máxima das últimas `range_lookback_4h` velas 4H
   FECHADAS (a anterior ainda não tinha fechado acima: rompimento novo), com volume >=
   breakout_volume_ratio × a média das velas 1H anteriores.
Entrada: limite no reteste do nível (nível + retest_offset_pct), válida por N velas — não persegue.
Stop: o mais próximo da entrada entre o meio do range e (nível − stop_atr_mult × ATR 1H),
com distância mínima de min_stop_atr × ATR.
"""

from __future__ import annotations

import pandas as pd

from bot.bybit.client import KLINE_INTERVAL_MS
from bot.indicators import atr
from bot.signals.base import TF_LABEL, Signal, closed_only


def breakout_signal(symbol: str, h1: pd.DataFrame, h4: pd.DataFrame, now_ms: int, squeeze_points: float,
                    score: float, cfg, ind, exits, trigger: str = "60", context: str = "240") -> Signal | None:
    """cfg = setups.rompimento_compressao, ind = indicators, exits = exits.

    h1/h4 = velas do tempo gráfico do gatilho e do contexto (padrão 1H/4H; intraday 15m/1H).
    """
    if squeeze_points < cfg.min_squeeze_points:
        return None
    h1 = closed_only(h1, trigger, now_ms)
    h4 = closed_only(h4, context, now_ms)
    tf, ctf = TF_LABEL[trigger], TF_LABEL[context]
    if len(h4) < cfg.range_lookback_4h or len(h1) < ind.volume_avg_period + ind.atr_period + 2:
        return None

    cur, prev = h1.iloc[-1], h1.iloc[-2]
    # o range usa só velas 4H que já tinham fechado antes da vela de rompimento começar
    rng = h4[h4["start_ms"] + KLINE_INTERVAL_MS[context] <= cur["start_ms"]].iloc[-cfg.range_lookback_4h:]
    if len(rng) < cfg.range_lookback_4h:
        return None
    level, range_low = float(rng["high"].max()), float(rng["low"].min())
    if not (cur["close"] > level >= prev["close"]):
        return None

    avg_volume = h1["volume"].iloc[-ind.volume_avg_period - 1:-1].mean()
    volume_ratio = cur["volume"] / avg_volume if avg_volume > 0 else 0.0
    if volume_ratio < cfg.breakout_volume_ratio:
        return None

    atr_now = float(atr(h1, ind.atr_period).iloc[-1])
    if pd.isna(atr_now) or atr_now <= 0:
        return None
    entry = level * (1 + cfg.retest_offset_pct / 100)
    mid = (level + range_low) / 2
    stop = max(mid, level - cfg.stop_atr_mult * atr_now)        # o mais próximo da entrada
    stop = min(stop, entry - cfg.min_stop_atr * atr_now)       # respeita a distância mínima
    risk = entry - stop
    if risk <= 0:
        return None
    return Signal(
        symbol=symbol, setup="rompimento_compressao", entry=entry, stop=stop,
        tp1=entry + exits.tp1_r * risk, tp2=entry + exits.tp2_r * risk,
        candle_start_ms=int(cur["start_ms"]), valid_candles=cfg.order_valid_candles_1h, score=score,
        reasons=(f"Compressão {squeeze_points:g} pts (mín. {cfg.min_squeeze_points:g})",
                 f"Vela {tf} fechou acima da máxima de {cfg.range_lookback_4h} velas {ctf} ({level:.6g})",
                 f"Volume {volume_ratio:.1f}× a média (mín. {cfg.breakout_volume_ratio:g}×)",
                 f"Entrada no reteste do nível + {cfg.retest_offset_pct:g}% (não persegue o preço)"),
        extra={"level": level, "range_low": range_low},
        interval_ms=KLINE_INTERVAL_MS[trigger],
    )
