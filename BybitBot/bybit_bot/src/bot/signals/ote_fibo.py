"""Setup 3 — ote_fibo (1H): porte de MQL5/Experts/ICT_FiboEntry_EA.mq5, só o lado comprado.

Lógica do EA (mantida):
1. Topos/fundos por fractais (`swing_bars` velas de cada lado, máximo/mínimo estrito).
2. Zigue-zague alternando topo/fundo (sequências do mesmo tipo ficam com o mais extremo);
   a última perna = penúltimo pivô -> último pivô, com tamanho >= min_leg_atr × ATR.
3. Fibonacci da perna: nível 0 = topo, 1 = origem. Zona OTE entre 61,8 % e 79 %.
4. Order Block: a partir da origem (no máximo `ob_lookback` velas antes do fim da perna), a
   primeira vela de alta com corpo >= displacement_atr × ATR é o deslocamento; a última vela de
   baixa antes dela é o OB. A zona de entrada é OTE ∩ OB.
5. Vela de rejeição (a última fechada): toca a zona, é de alta e fecha acima da zona.
6. Stop abaixo do OB / origem da perna + buffer; alvos 50 % da perna, topo, extensão 1,618.

Correções em relação ao EA original (documentadas no 06/Notion):
- O EA trata o índice 0 como a vela mais recente, mas copia os dados sem ArraySetAsSeries
  (índice 0 = mais antiga). Aqui tudo é cronológico e explícito.
- No lado comprado o EA monta a zona com topo/fundo invertidos, e a interseção com o OB fica
  sempre vazia (nunca compraria). Aqui a zona é [mín, máx] dos dois níveis.
Extras de segurança: a perna é invalidada se algum fechamento depois do topo ficou abaixo da
origem, e só a PRIMEIRA vela de rejeição de cada perna gera sinal (o EA guardava esse estado).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bot.bybit.client import KLINE_INTERVAL_MS
from bot.indicators import atr
from bot.signals.base import TF_LABEL, Signal, closed_only


@dataclass(frozen=True)
class Pivot:
    pos: int        # posição (iloc) da vela
    price: float
    is_high: bool


@dataclass(frozen=True)
class Leg:
    start: Pivot    # origem (fundo, numa perna de alta)
    end: Pivot      # topo

    @property
    def bullish(self) -> bool:
        return not self.start.is_high and self.end.is_high

    @property
    def size(self) -> float:
        return abs(self.end.price - self.start.price)

    def price_at(self, level: float) -> float:
        """Nível de Fibonacci: 0 = fim da perna (topo), 1 = origem."""
        return self.end.price + level * (self.start.price - self.end.price)


def find_pivots(df: pd.DataFrame, bars: int) -> list[Pivot]:
    """Topos/fundos com `bars` velas de cada lado (estritamente maior/menor), em ordem cronológica."""
    high, low = df["high"].to_numpy(float), df["low"].to_numpy(float)
    n = len(df)
    if n < 2 * bars + 1:
        return []
    win_h = np.lib.stride_tricks.sliding_window_view(high, 2 * bars + 1)
    win_l = np.lib.stride_tricks.sliding_window_view(low, 2 * bars + 1)
    center_h, center_l = win_h[:, bars], win_l[:, bars]
    others_h = np.delete(win_h, bars, axis=1)
    others_l = np.delete(win_l, bars, axis=1)
    is_high = center_h > others_h.max(axis=1)
    is_low = center_l < others_l.min(axis=1)
    pivots = []
    for k in np.flatnonzero(is_high | is_low):
        i = int(k) + bars
        if is_high[k]:
            pivots.append(Pivot(i, float(high[i]), True))
        if is_low[k]:
            pivots.append(Pivot(i, float(low[i]), False))
    return pivots


def zigzag(pivots: list[Pivot]) -> list[Pivot]:
    """Alterna topo/fundo; em sequência do mesmo tipo fica o mais extremo (empate: o mais antigo)."""
    out: list[Pivot] = []
    for p in pivots:
        if out and out[-1].is_high == p.is_high:
            better = p.price > out[-1].price if p.is_high else p.price < out[-1].price
            if better:
                out[-1] = p
        else:
            out.append(p)
    return out


def last_leg(df: pd.DataFrame, bars: int) -> Leg | None:
    zz = zigzag(find_pivots(df, bars))
    return Leg(zz[-2], zz[-1]) if len(zz) >= 2 else None


def find_order_block(df: pd.DataFrame, leg: Leg, atr_value: float, displacement_atr: float, lookback: int
                     ) -> tuple[float, float, int] | None:
    """(mínima, máxima, posição) da última vela de baixa antes da vela de deslocamento."""
    o, c = df["open"].to_numpy(float), df["close"].to_numpy(float)
    first = max(leg.start.pos, leg.end.pos - lookback)
    for i in range(first, leg.end.pos):
        if c[i] > o[i] and (c[i] - o[i]) >= displacement_atr * atr_value:
            for j in range(i - 1, first - 1, -1):
                if c[j] < o[j]:
                    return float(df["low"].iloc[j]), float(df["high"].iloc[j]), j
            return None
    return None


def ote_signal(symbol: str, h1: pd.DataFrame, now_ms: int, score: float, cfg, ind, trigger: str = "60"
               ) -> Signal | None:
    """cfg = setups.ote_fibo, ind = indicators; h1 = velas do tempo gráfico do gatilho."""
    h1 = closed_only(h1, trigger, now_ms).reset_index(drop=True)
    tf = TF_LABEL[trigger]
    if len(h1) < 2 * cfg.swing_bars + ind.atr_period + 5:
        return None
    atr_value = float(atr(h1, ind.atr_period).iloc[-1])
    if np.isnan(atr_value) or atr_value <= 0:
        return None
    leg = last_leg(h1, cfg.swing_bars)
    if leg is None or not leg.bullish or leg.size < cfg.min_leg_atr * atr_value:
        return None

    after = h1.iloc[leg.end.pos + 1:]
    if after.empty or (after["close"] < leg.start.price).any():
        return None  # sem velas depois do topo, ou a perna foi invalidada

    a, b = leg.price_at(cfg.ote_start), leg.price_at(cfg.ote_end)
    zone_low, zone_high = min(a, b), max(a, b)
    ob = None
    if cfg.use_order_block:
        ob = find_order_block(h1, leg, atr_value, cfg.displacement_atr, cfg.ob_lookback)
        if ob is None:
            return None
        zone_low, zone_high = max(zone_low, ob[0]), min(zone_high, ob[1])
        if zone_low > zone_high:
            return None  # OTE e OB não se encontram

    def rejects(row: pd.Series) -> bool:
        return row["low"] <= zone_high and row["high"] >= zone_low and row["close"] > row["open"] \
            and row["close"] > zone_high

    hits = [i for i in range(len(after)) if rejects(after.iloc[i])]
    if not hits or hits[0] != len(after) - 1:
        return None  # nenhuma rejeição, ou a primeira já aconteceu antes desta vela

    cur = after.iloc[-1]
    entry = float(cur["close"]) * (1 + cfg.entry_tolerance_pct / 100)
    edge = min(ob[0], leg.start.price) if ob else leg.start.price
    stop = edge - cfg.stop_atr_buffer * atr_value
    if entry - stop <= 0:
        return None
    tp3 = leg.price_at(-(cfg.tp3_extension - 1))
    return Signal(
        symbol=symbol, setup="ote_fibo", entry=entry, stop=stop,
        tp1=leg.price_at(cfg.tp1_level), tp2=leg.price_at(cfg.tp2_level),
        candle_start_ms=int(cur["start_ms"]), valid_candles=cfg.order_valid_candles_1h, score=score,
        reasons=(f"Perna de alta {leg.start.price:.6g} → {leg.end.price:.6g} ({leg.size / atr_value:.1f}× ATR {tf})",
                 f"Retração até a zona OTE {cfg.ote_start * 100:.1f}–{cfg.ote_end * 100:.0f}%"
                 + (" com Order Block" if ob else ""),
                 f"Vela {tf} de rejeição fechou acima da zona",
                 f"Alvos: 50% da perna, topo e extensão {cfg.tp3_extension:g} ({tp3:.6g})"),
        extra={"tp3": tp3, "leg_start": leg.start.price, "leg_end": leg.end.price,
               "zone": (zone_low, zone_high), "order_block": ob[:2] if ob else None},
        interval_ms=KLINE_INTERVAL_MS[trigger],
    )
