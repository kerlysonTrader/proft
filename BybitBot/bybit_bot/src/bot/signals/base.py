"""Estrutura comum dos sinais de entrada (seção 4 do 03_ESTRATEGIA.md).

Todo setup é uma função pura sobre velas FECHADAS: recebe DataFrames e `now_ms` e
devolve um Signal ou None. `closed_only` descarta por segurança qualquer vela que
ainda esteja em formação, mesmo que alguém a passe por engano.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd

from bot.bybit.client import KLINE_INTERVAL_MS

# Códigos curtos no orderLinkId: a Bybit aceita no máximo 36 caracteres
SETUP_CODES = {"pullback_tendencia": "pb", "rompimento_compressao": "bo", "ote_fibo": "ote"}


@dataclass(frozen=True)
class Signal:
    symbol: str
    setup: str
    entry: float
    stop: float
    tp1: float
    tp2: float
    candle_start_ms: int          # abertura da vela 1H que gerou o sinal
    valid_candles: int            # validade da ordem limite, em velas 1H
    score: float = 0.0
    reasons: tuple[str, ...] = field(default_factory=tuple)
    extra: dict = field(default_factory=dict)  # ex.: tp3 do ote_fibo, nível rompido

    @property
    def risk(self) -> float:
        return self.entry - self.stop

    @property
    def rr(self) -> float:
        """R:R até o TP2."""
        return (self.tp2 - self.entry) / self.risk if self.risk > 0 else float("nan")

    @property
    def stop_pct(self) -> float:
        return self.risk / self.entry * 100 if self.entry else float("nan")

    @property
    def valid_until_ms(self) -> int:
        """Fim da validade: a vela do sinal fecha e mais `valid_candles` velas 1H."""
        return self.candle_start_ms + (1 + self.valid_candles) * KLINE_INTERVAL_MS["60"]

    @property
    def order_link_id(self) -> str:
        stamp = datetime.fromtimestamp(self.candle_start_ms / 1000, tz=UTC).strftime("%Y%m%d%H%M")
        return f"{self.symbol}-{SETUP_CODES[self.setup]}-{stamp}"[:36]


def closed_only(df: pd.DataFrame, interval: str, now_ms: int) -> pd.DataFrame:
    """Só as velas cujo período já terminou."""
    if df.empty:
        return df
    end = df["start_ms"] + KLINE_INTERVAL_MS[interval]
    return df[end <= now_ms]


def body_fraction(row: pd.Series) -> float:
    span = row["high"] - row["low"]
    return abs(row["close"] - row["open"]) / span if span > 0 else 0.0


def is_bullish_engulfing(prev: pd.Series, cur: pd.Series) -> bool:
    return (prev["close"] < prev["open"] and cur["close"] > cur["open"]
            and cur["close"] >= prev["open"] and cur["open"] <= prev["close"])
