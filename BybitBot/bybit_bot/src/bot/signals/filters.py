"""Filtros comuns a todos os setups (seção 4 do 03_ESTRATEGIA.md).

- R:R até o TP2 >= min_rr_tp2
- distância do stop entre min_stop_pct e max_stop_pct do preço de entrada
- regime permite novas entradas (≠ risk_off e sem circuit breaker)
- spread ok no momento
- sem posição aberta na moeda; sem reentrada por reentry_cooldown_hours depois de um stop
O veto do Gemini (seção 5) entra na Fase 6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from bot.signals.base import Signal

HOUR_MS = 3_600_000


@dataclass
class SignalContext:
    now_ms: int
    allow_new_entries: bool = True                     # Regime.allow_new_entries
    regime: str = "risk_on"
    spread_pct: dict[str, float] = field(default_factory=dict)
    open_symbols: set[str] = field(default_factory=set)
    last_stop_ms: dict[str, int] = field(default_factory=dict)


def check_filters(signal: Signal, ctx: SignalContext, common, max_spread_pct: float) -> list[str]:
    """Lista de motivos de rejeição (vazia = aprovado). common = setups.common."""
    problems = []
    rr = signal.rr
    if math.isnan(rr) or rr < common.min_rr_tp2:
        problems.append(f"R:R até o TP2 {rr:.2f} < {common.min_rr_tp2:g}")
    stop_pct = signal.stop_pct
    if stop_pct < common.min_stop_pct:
        problems.append(f"stop curto demais: {stop_pct:.2f}% < {common.min_stop_pct:g}%")
    elif stop_pct > common.max_stop_pct:
        problems.append(f"stop longo demais: {stop_pct:.2f}% > {common.max_stop_pct:g}%")
    if not ctx.allow_new_entries:
        problems.append(f"regime {ctx.regime} / circuit breaker: sem novas entradas")
    spread = ctx.spread_pct.get(signal.symbol)
    if spread is None or math.isnan(spread) or spread > max_spread_pct:
        problems.append(f"spread {spread if spread is not None else '?'}% acima de {max_spread_pct:g}%")
    if signal.symbol in ctx.open_symbols:
        problems.append("já existe posição aberta nesta moeda")
    last_stop = ctx.last_stop_ms.get(signal.symbol)
    if last_stop is not None and ctx.now_ms - last_stop < common.reentry_cooldown_hours * HOUR_MS:
        problems.append(f"stop há menos de {common.reentry_cooldown_hours:g} h nesta moeda")
    return problems
