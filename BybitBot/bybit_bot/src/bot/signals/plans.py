"""Planos de entrada/saída para o painel (Scanner), com as MESMAS regras dos setups.

Não é sinal: mostra onde cada setup compraria, qual gatilho falta, o stop estimado e os alvos.
- Pullback: zona entre a EMA50 e a EMA20 do 1H; gatilho = vela 1H de confirmação (RSI volta acima
  de 45); stop estimado = fundo da zona − buffer × ATR 1H (no sinal real usa a mínima do recuo).
- Rompimento: nível = máxima das últimas N velas 4H fechadas; gatilho = vela 1H fechando acima com
  volume; entrada no reteste; stop = o mais próximo entre o meio do range e nível − k × ATR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from bot.indicators import atr, ema
from bot.signals.base import closed_only


@dataclass(frozen=True)
class Plan:
    setup: str
    entry: float
    stop: float
    tp1: float
    tp2: float
    zone: tuple[float, float] | None
    trigger: str
    price_vs_zone: str = ""   # acima | na_zona | abaixo (só no pullback)

    @property
    def stop_pct(self) -> float:
        return (self.entry - self.stop) / self.entry * 100 if self.entry else float("nan")


def fmt_price(value: float) -> str:
    return f"{value:.6g}".replace(".", ",")


def _br(value: float, spec: str = "g") -> str:
    """Número com vírgula decimal (padrão do painel)."""
    return format(value, spec).replace(".", ",")


def _targets(entry: float, stop: float, exits: Any) -> tuple[float, float]:
    risk = entry - stop
    return entry + exits.tp1_r * risk, entry + exits.tp2_r * risk


def entry_plans(h1: pd.DataFrame, h4: pd.DataFrame, components: dict[str, float], now_ms: int, config: Any
                ) -> list[Plan]:
    st, ind, exits = config.setups, config.indicators, config.exits
    h1 = closed_only(h1, "60", now_ms)
    h4 = closed_only(h4, "240", now_ms)
    plans: list[Plan] = []
    if len(h1) < ind.ema_mid + 2:
        return plans
    close = float(h1["close"].iloc[-1])
    atr1 = float(atr(h1, ind.atr_period).iloc[-1])

    pb = st.pullback_tendencia
    if components.get("trend", 0) >= pb.min_trend_points and atr1 == atr1:
        e20 = float(ema(h1["close"], ind.ema_short).iloc[-1])
        e50 = float(ema(h1["close"], ind.ema_mid).iloc[-1])
        low, high = min(e20, e50), max(e20, e50)
        entry = high * (1 + pb.entry_tolerance_pct / 100)
        stop = low - pb.stop_atr_buffer * atr1
        tp1, tp2 = _targets(entry, stop, exits)
        plans.append(Plan("pullback_tendencia", entry, stop, tp1, tp2, (low, high),
                          f"vela 1H fechando acima da EMA20 com corpo ≥ {pb.min_body_fraction:.0%} e RSI 1H "
                          f"voltando acima de {_br(pb.rsi_touch_band_1h[1])}",
                          price_vs_zone="acima" if close > high else "abaixo" if close < low else "na_zona"))

    bo = st.rompimento_compressao
    if components.get("squeeze", 0) >= bo.min_squeeze_points and len(h4) >= bo.range_lookback_4h and atr1 == atr1:
        rng = h4.iloc[-bo.range_lookback_4h:]
        level, range_low = float(rng["high"].max()), float(rng["low"].min())
        entry = level * (1 + bo.retest_offset_pct / 100)
        stop = max((level + range_low) / 2, level - bo.stop_atr_mult * atr1)
        stop = min(stop, entry - bo.min_stop_atr * atr1)
        tp1, tp2 = _targets(entry, stop, exits)
        plans.append(Plan("rompimento_compressao", entry, stop, tp1, tp2, None,
                          f"vela 1H fechando acima de {fmt_price(level)} com volume ≥ {_br(bo.breakout_volume_ratio)}× "
                          f"a média; compra no reteste"))
    return plans


def plan_lines(plans: list[Plan], common: Any, exits: Any) -> list[str]:
    """Texto para a lista de motivos do painel."""
    if not plans:
        return ["Plano: nenhum setup aplicável agora (tendência e compressão abaixo do mínimo)"]
    lines = []
    for p in plans:
        name = "Pullback" if p.setup == "pullback_tendencia" else "Rompimento"
        where = (f"zona de compra {fmt_price(p.zone[0])}–{fmt_price(p.zone[1])}" if p.zone
                 else f"entrada {fmt_price(p.entry)}")
        status = {"acima": " (aguardando o recuo até a zona)", "na_zona": " (preço já na zona)",
                  "abaixo": " (preço abaixo da zona: precisa recuperar a EMA20 1H)"}.get(p.price_vs_zone, "")
        stop_ok = common.min_stop_pct <= p.stop_pct <= common.max_stop_pct
        warn = "" if stop_ok else (f" — stop {_br(p.stop_pct, '.1f')}% fora da faixa {_br(common.min_stop_pct)}–"
                                   f"{_br(common.max_stop_pct)}%: o sinal seria barrado")
        lines.append(f"Plano {name}: {where}{status}; gatilho: {p.trigger}; stop ~{fmt_price(p.stop)} "
                     f"({_br(p.stop_pct, '.1f')}%); alvos {fmt_price(p.tp1)} ({_br(exits.tp1_r)}R) / "
                     f"{fmt_price(p.tp2)} ({_br(exits.tp2_r)}R){warn}")
    lines.append("⚠ Planos informativos: a estratégia ainda não passou no backtest (Gate 5) — não é recomendação")
    return lines
