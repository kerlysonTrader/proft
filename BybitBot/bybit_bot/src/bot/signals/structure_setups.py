"""Setups de estrutura (intraday: gatilho 15m, contexto 1H). Todos de COMPRA; a venda roda as mesmas
regras no gráfico invertido (signals/direction.py), como os demais setups.

Contexto no tempo gráfico maior (setups.estrutura.context):
- "dow_e_media" (padrão): Dow em alta E fechamento acima da MME50;
- "dow": só Dow em alta;  "media": fechamento acima da MME50 e MME21 > MME50.
Gatilho na vela que acabou de fechar (detectores em signals/structure.py):
- estrutura_bos: BOS de alta (rompe o último topo);
- estrutura_choch: CHoCH de alta (o recuo do tempo menor vira para alta a favor do maior);
- lt_rompimento: quebra da LTB com pelo menos min_line_touches toques;
- cunha: rompimento de cunha de baixa (falling wedge);
- medias_cruzamento: MME9 cruza acima da MME21 com o fechamento acima da MME200.
Entrada: limite no fechamento + entry_tolerance_pct, válida por order_valid_candles velas.
Stop: último fundo confirmado − stop_atr_buffer × ATR, com distância mínima de min_stop_atr × ATR.
Alvos: exits.tp1_r e exits.tp2_r vezes o risco.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from bot.bybit.client import KLINE_INTERVAL_MS
from bot.signals.base import TF_LABEL, Signal, closed_only
from bot.signals.structure import StructureParams, row_at, structure_arrays

STRUCTURE_SETUPS = ("estrutura_bos", "estrutura_choch", "lt_rompimento", "cunha", "medias_cruzamento")
TRIGGER_KEY = {"estrutura_bos": "bos_up", "estrutura_choch": "choch_up", "lt_rompimento": "ltb_break",
               "cunha": "wedge_up", "medias_cruzamento": "cross_up"}
TRIGGER_TEXT = {"estrutura_bos": "BOS de alta (fechou acima do último topo)",
                "estrutura_choch": "CHoCH de alta (o recuo virou para alta)",
                "lt_rompimento": "quebra da LTB", "cunha": "rompimento de cunha de baixa",
                "medias_cruzamento": "MME9 cruzou acima da MME21"}


def enabled_structure(config: Any) -> list[str]:
    return [s for s in config.setups.enabled if s in STRUCTURE_SETUPS]


def context_ok(c: dict[str, float], mode: str) -> bool:
    dow = c["trend"] == 1
    above = c["close"] > c["ema_mid"]
    if mode == "dow":
        return dow
    if mode == "media":
        return above and c["ema_slow"] > c["ema_mid"]
    return dow and above


def structure_signals(symbol: str, t: dict[str, float], c: dict[str, float], candle_start_ms: int, score: float,
                      config: Any, enabled: list[str]) -> list[Signal]:
    """t = leitura da vela do gatilho que acabou de fechar; c = do último contexto fechado."""
    st, exits = config.setups, config.exits
    cfg = st.estrutura
    tf, ctf = TF_LABEL[st.trigger_interval], TF_LABEL[st.context_interval]
    fired = [s for s in enabled if t.get(TRIGGER_KEY[s])]
    if not fired or not context_ok(c, cfg.context):
        return []
    atr_now, close, last_low = t["atr"], t["close"], t["last_low"]
    if not (atr_now == atr_now and atr_now > 0 and last_low == last_low):
        return []
    out = []
    for setup in fired:
        touches = t["ltb_touches"]
        if setup == "lt_rompimento" and touches == touches and touches < cfg.min_line_touches:
            continue
        if setup == "medias_cruzamento" and not close > t["ema_long"]:
            continue
        entry = close * (1 + cfg.entry_tolerance_pct / 100)
        stop = min(last_low - cfg.stop_atr_buffer * atr_now, entry - cfg.min_stop_atr * atr_now)
        risk = entry - stop
        if risk <= 0:
            continue
        out.append(Signal(
            symbol=symbol, setup=setup, entry=entry, stop=stop,
            tp1=entry + exits.tp1_r * risk, tp2=entry + exits.tp2_r * risk,
            candle_start_ms=candle_start_ms, valid_candles=cfg.order_valid_candles, score=score,
            reasons=(f"Contexto {ctf}: Dow {'alta' if c['trend'] == 1 else 'não-alta'}, preço "
                     f"{'acima' if c['close'] > c['ema_mid'] else 'abaixo'} da MME50",
                     f"Gatilho {tf}: {TRIGGER_TEXT[setup]}",
                     f"Stop no último fundo {tf} ({last_low:.6g}) − {cfg.stop_atr_buffer:g} × ATR"),
            extra={"level": t["break_level"] if t["break_level"] == t["break_level"] else None},
            interval_ms=KLINE_INTERVAL_MS[st.trigger_interval],
        ))
    return out


def structure_signals_live(symbol: str, trig: pd.DataFrame, ctx: pd.DataFrame, now_ms: int, score: float,
                           config: Any) -> list[Signal]:
    """Mesmo cálculo do backtest, a partir das velas (robô ao vivo e scanners)."""
    enabled = enabled_structure(config)
    if not enabled:
        return []
    st = config.setups
    trig = closed_only(trig, st.trigger_interval, now_ms)
    ctx = closed_only(ctx, st.context_interval, now_ms)
    if len(trig) < 60 or len(ctx) < 60:
        return []
    params = StructureParams.from_config(st.estrutura, config.indicators.atr_period)
    t = row_at(structure_arrays(trig, params), len(trig) - 1)
    c = row_at(structure_arrays(ctx, params), len(ctx) - 1)
    return structure_signals(symbol, t, c, int(trig["start_ms"].iat[-1]), score, config, enabled)
