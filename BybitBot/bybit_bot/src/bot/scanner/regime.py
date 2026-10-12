"""Regime de mercado pelo BTC (seção 2 do 03_ESTRATEGIA.md).

risk_on  : BTC fecha acima da EMA200 diária E EMA50 4H > EMA200 4H
neutro   : só uma das duas         -> risco ÷ 2, máx. de posições menor, score mínimo maior
risk_off : nenhuma                 -> não abre novas posições
Extras: amplitude (% do universo acima da EMA50 4H) abaixo do mínimo -> risk_off;
circuit breaker: BTC caiu mais que o limite em 24 h -> sem novas entradas por N horas.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from bot.indicators import ema

HOUR_MS = 3_600_000


@dataclass
class RegimeState:
    """Estado que sobrevive entre varreduras (pausa do circuit breaker)."""
    circuit_until_ms: int | None = None

    @classmethod
    def load(cls, path: str | Path) -> RegimeState:
        try:
            return cls(**json.loads(Path(path).read_text(encoding="utf-8")))
        except (FileNotFoundError, ValueError, TypeError):
            return cls()

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(asdict(self)), encoding="utf-8")


@dataclass
class Regime:
    regime: str                      # risk_on | neutro | risk_off
    btc_above_ema200_1d: bool | None
    btc_ema50_above_ema200_4h: bool | None
    breadth_pct: float | None
    btc_change_24h_pct: float | None
    circuit_breaker_active: bool
    circuit_until_ms: int | None
    reasons: list[str] = field(default_factory=list)

    @property
    def allow_new_entries(self) -> bool:
        return self.regime != "risk_off" and not self.circuit_breaker_active


def _cond(series_a: pd.Series, series_b: pd.Series) -> bool | None:
    a, b = series_a.iloc[-1] if len(series_a) else None, series_b.iloc[-1] if len(series_b) else None
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return None
    return bool(a > b)


def breadth_pct(closes_vs_ema: list[bool]) -> float | None:
    """% das moedas com fechamento 4H acima da EMA50 4H."""
    return 100 * sum(closes_vs_ema) / len(closes_vs_ema) if closes_vs_ema else None


def evaluate_regime(btc_d1: pd.DataFrame, btc_h4: pd.DataFrame, btc_h1: pd.DataFrame, breadth: float | None,
                    state: RegimeState, now_ms: int, rc) -> Regime:
    """rc = RegimeConfig. Atualiza `state` se o circuit breaker disparar."""
    above_200d = _cond(btc_d1["close"], ema(btc_d1["close"], rc.daily_ema)) if len(btc_d1) else None
    ema_fast = ema(btc_h4["close"], rc.h4_fast_ema) if len(btc_h4) else pd.Series(dtype=float)
    ema_slow = ema(btc_h4["close"], rc.h4_slow_ema) if len(btc_h4) else pd.Series(dtype=float)
    cross_4h = _cond(ema_fast, ema_slow)

    reasons: list[str] = []
    met = sum(bool(c) for c in (above_200d, cross_4h))
    if above_200d is None or cross_4h is None:
        regime = "risk_off"
        reasons.append("Dados do BTC insuficientes para as EMAs: tratado como risk_off")
    else:
        regime = {2: "risk_on", 1: "neutro", 0: "risk_off"}[met]
        reasons.append(f"BTC {'acima' if above_200d else 'abaixo'} da EMA{rc.daily_ema} diária")
        reasons.append(f"EMA{rc.h4_fast_ema} 4H {'acima' if cross_4h else 'abaixo'} da EMA{rc.h4_slow_ema} 4H")

    if breadth is not None and breadth < rc.min_breadth_pct and regime != "risk_off":
        reasons.append(f"Amplitude {breadth:.0f}% < {rc.min_breadth_pct:g}%: tratado como risk_off")
        regime = "risk_off"
    elif breadth is not None:
        reasons.append(f"Amplitude: {breadth:.0f}% do universo acima da EMA50 4H")

    change_24h = None
    if len(btc_h1) > 24:
        closes = btc_h1["close"]
        change_24h = float(closes.iloc[-1] / closes.iloc[-25] - 1) * 100
        if change_24h < -rc.circuit_breaker_btc_drop_24h_pct:
            until = now_ms + int(rc.circuit_breaker_pause_hours * HOUR_MS)
            state.circuit_until_ms = max(state.circuit_until_ms or 0, until)
            reasons.append(f"BTC caiu {abs(change_24h):.1f}% em 24h: circuit breaker acionado")
    active = state.circuit_until_ms is not None and now_ms < state.circuit_until_ms
    if active:
        reasons.append("Circuit breaker ativo: sem novas entradas até o fim da pausa")

    return Regime(regime, above_200d, cross_4h, breadth, change_24h, active,
                  state.circuit_until_ms if active else None, reasons)
