"""Lado vendido pelo gráfico INVERTIDO (preço' = 1/preço).

No gráfico invertido, uma queda vira alta: os mesmos setups, features e score de compra (já
validados) encontram as oportunidades de VENDA. Os níveis voltam ao preço real por 1/x:
entrada' -> entrada, stop' (abaixo) -> stop ACIMA da entrada, alvos' (acima) -> alvos ABAIXO.

Os indicadores são calculados sobre 1/preço; para movimentos pequenos (intraday, poucos %),
1/x preserva as distâncias relativas quase exatamente (diferença de segunda ordem), por isso o R
de uma venda no preço real fica muito próximo do R no gráfico invertido.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from bot.signals.base import Signal


def invert_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Velas do gráfico invertido: abertura/fechamento = 1/x; máxima' = 1/mínima; mínima' = 1/máxima."""
    if df.empty:
        return df.copy()
    out = df.copy()
    out["open"] = 1 / df["open"]
    out["close"] = 1 / df["close"]
    out["high"] = 1 / df["low"]
    out["low"] = 1 / df["high"]
    return out


R_TARGET_SETUPS = {"pullback_tendencia", "rompimento_compressao"}


def to_short(signal: Signal, exits=None) -> Signal:
    """Converte um sinal de compra encontrado no gráfico invertido numa VENDA no preço real.

    Entrada e stop vêm da estrutura (convertidos por 1/x). Nos setups com alvos em múltiplos de R,
    se `exits` for passado os alvos são recalculados no preço real (R:R exato); no ote_fibo os
    alvos são níveis da perna e só são convertidos.
    """
    short = _convert(signal)
    if exits is not None and signal.setup in R_TARGET_SETUPS:
        risk = short.stop - short.entry
        short = replace(short, tp1=short.entry - exits.tp1_r * risk, tp2=short.entry - exits.tp2_r * risk)
    return short


def _convert(signal: Signal) -> Signal:
    extra = dict(signal.extra)
    for key in ("level", "range_low", "tp3", "leg_start", "leg_end"):
        if isinstance(extra.get(key), float | int):
            extra[key] = 1 / extra[key]
    for key in ("zone", "order_block"):
        if extra.get(key):
            low, high = extra[key]
            extra[key] = (1 / high, 1 / low)
    return replace(signal, entry=1 / signal.entry, stop=1 / signal.stop, tp1=1 / signal.tp1, tp2=1 / signal.tp2,
                   direction=-1, extra=extra,
                   reasons=("Venda pelo gráfico invertido (mesmas regras da compra, espelhadas)", *signal.reasons))
