"""Roda os setups habilitados para a Watchlist A e aplica os filtros comuns.

Cada setup recebe só velas FECHADAS. Um sinal aprovado vai ao painel como `signal`
(status "pendente"); rejeitados ficam no log com o motivo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from bot.logging_setup import get_logger
from bot.signals.base import Signal
from bot.signals.breakout import breakout_signal
from bot.signals.filters import SignalContext, check_filters
from bot.signals.ote_fibo import ote_signal
from bot.signals.pullback import pullback_signal

log = get_logger("signals")


@dataclass
class Evaluation:
    signal: Signal
    problems: list[str]

    @property
    def approved(self) -> bool:
        return not self.problems


def evaluate_setups(symbol: str, h1: pd.DataFrame, h4: pd.DataFrame, now_ms: int, components: dict[str, float],
                    score: float, config: Any) -> list[Signal]:
    """Sinais brutos (antes dos filtros) de todos os setups habilitados."""
    st, ind, exits = config.setups, config.indicators, config.exits
    found = []
    if "pullback_tendencia" in st.enabled:
        found.append(pullback_signal(symbol, h1, h4, now_ms, components.get("trend", 0), score,
                                     st.pullback_tendencia, ind, exits))
    if "rompimento_compressao" in st.enabled:
        found.append(breakout_signal(symbol, h1, h4, now_ms, components.get("squeeze", 0), score,
                                     st.rompimento_compressao, ind, exits))
    if "ote_fibo" in st.enabled:
        found.append(ote_signal(symbol, h1, now_ms, score, st.ote_fibo, ind))
    return [s for s in found if s is not None]


def evaluate(symbol: str, h1: pd.DataFrame, h4: pd.DataFrame, components: dict[str, float], score: float,
             ctx: SignalContext, config: Any) -> list[Evaluation]:
    out = []
    for signal in evaluate_setups(symbol, h1, h4, ctx.now_ms, components, score, config):
        problems = check_filters(signal, ctx, config.setups.common, config.universe.max_spread_pct)
        out.append(Evaluation(signal, problems))
        log.info("sinal aprovado" if not problems else "sinal rejeitado pelos filtros",
                 extra={"symbol": symbol, "data": {"setup": signal.setup, "entry": signal.entry,
                                                   "stop": signal.stop, "rr": round(signal.rr, 2),
                                                   "problemas": problems}})
    return out


def signal_payload(signal: Signal, status: str = "pendente") -> dict[str, Any]:
    """Payload do evento `signal` (05_DASHBOARD_E_INTEGRACAO.md)."""
    return {
        "symbol": signal.symbol,
        "setup": signal.setup,
        "entry": signal.entry,
        "stop": signal.stop,
        "tp1": signal.tp1,
        "tp2": signal.tp2,
        "rr": round(signal.rr, 2),
        "score": round(signal.score, 1),
        "status": status,
        "reason": "; ".join(signal.reasons),
        "order_link_id": signal.order_link_id,
    }
