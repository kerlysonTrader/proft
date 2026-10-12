"""Planos de entrada/saída para o painel (Scanner), com as MESMAS regras dos setups.

Não é sinal: mostra onde cada setup entraria, qual gatilho falta, o stop estimado e os alvos.
Tempos gráficos = setups.trigger_interval (gatilho) e setups.context_interval (contexto):
1H/4H no padrão, 15m/1H no intraday.
- Pullback: zona entre a EMA50 e a EMA20 do gatilho; gatilho = vela de confirmação (RSI volta acima
  de 45); stop estimado = fundo da zona − buffer × ATR (no sinal real usa a mínima do recuo).
- Rompimento: nível = máxima das últimas N velas de contexto fechadas; gatilho = vela fechando acima
  com volume; entrada no reteste; stop = o mais próximo entre o meio do range e nível − k × ATR.

VENDA (direction = −1): as velas chegam INVERTIDAS (1/preço, ver signals/direction.py); o plano é
calculado como compra no gráfico invertido e devolvido no preço real (stop acima, alvos abaixo).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from bot.indicators import atr, ema
from bot.signals.base import TF_LABEL, closed_only

DEFAULT_FOOTER = "⚠ Planos informativos: a estratégia ainda não passou no backtest (Gate 5) — não é recomendação"


@dataclass(frozen=True)
class Plan:
    setup: str
    entry: float
    stop: float
    tp1: float
    tp2: float
    zone: tuple[float, float] | None
    trigger: str
    price_vs_zone: str = ""   # aguardando | na_zona | contra (só no pullback)
    direction: int = 1        # 1 = compra, −1 = venda

    @property
    def stop_pct(self) -> float:
        return (self.entry - self.stop) * self.direction / self.entry * 100 if self.entry else float("nan")


def fmt_price(value: float) -> str:
    return f"{value:.6g}".replace(".", ",")


def _br(value: float, spec: str = "g") -> str:
    """Número com vírgula decimal (padrão do painel)."""
    return format(value, spec).replace(".", ",")


def _targets(entry: float, stop: float, exits: Any) -> tuple[float, float]:
    risk = entry - stop
    return entry + exits.tp1_r * risk, entry + exits.tp2_r * risk


def entry_plans(trig: pd.DataFrame, ctx: pd.DataFrame, components: dict[str, float], now_ms: int, config: Any,
                direction: int = 1) -> list[Plan]:
    """Planos dos setups aplicáveis. trig/ctx = velas do gatilho e do contexto (invertidas na venda)."""
    st, ind, exits = config.setups, config.indicators, config.exits
    t_iv, c_iv = st.trigger_interval, st.context_interval
    tl = TF_LABEL[t_iv]
    trig = closed_only(trig, t_iv, now_ms)
    ctx = closed_only(ctx, c_iv, now_ms)
    short = direction < 0
    up = "abaixo" if short else "acima"   # sentido do gatilho no preço real
    plans: list[Plan] = []
    if len(trig) < ind.ema_mid + 2:
        return plans
    close = float(trig["close"].iloc[-1])
    atr_t = float(atr(trig, ind.atr_period).iloc[-1])

    pb = st.pullback_tendencia
    if components.get("trend", 0) >= pb.min_trend_points and atr_t == atr_t:
        e20 = float(ema(trig["close"], ind.ema_short).iloc[-1])
        e50 = float(ema(trig["close"], ind.ema_mid).iloc[-1])
        low, high = min(e20, e50), max(e20, e50)
        entry = high * (1 + pb.entry_tolerance_pct / 100)
        stop = low - pb.stop_atr_buffer * atr_t
        rsi_level = pb.rsi_touch_band_1h[1]
        rsi_level = 100 - rsi_level if short else rsi_level   # RSI(1/x) ≈ 100 − RSI(x)
        plans.append(_finish(Plan(
            "pullback_tendencia", entry, stop, *_targets(entry, stop, exits), (low, high),
            f"vela {tl} fechando {up} da EMA20 com corpo ≥ {pb.min_body_fraction:.0%} e RSI {tl} "
            f"voltando {up} de {_br(rsi_level)}",
            price_vs_zone="aguardando" if close > high else "contra" if close < low else "na_zona"), short))

    bo = st.rompimento_compressao
    if components.get("squeeze", 0) >= bo.min_squeeze_points and len(ctx) >= bo.range_lookback_4h and atr_t == atr_t:
        rng = ctx.iloc[-bo.range_lookback_4h:]
        level, range_low = float(rng["high"].max()), float(rng["low"].min())
        entry = level * (1 + bo.retest_offset_pct / 100)
        stop = max((level + range_low) / 2, level - bo.stop_atr_mult * atr_t)
        stop = min(stop, entry - bo.min_stop_atr * atr_t)
        real_level = 1 / level if short else level
        plans.append(_finish(Plan(
            "rompimento_compressao", entry, stop, *_targets(entry, stop, exits), None,
            f"vela {tl} fechando {up} de {fmt_price(real_level)} com volume ≥ {_br(bo.breakout_volume_ratio)}× "
            f"a média; {'venda' if short else 'compra'} no reteste"), short))
    return plans


def _finish(plan: Plan, short: bool) -> Plan:
    """Venda: devolve o plano do gráfico invertido no preço real, com alvos exatos em R."""
    if not short:
        return plan
    entry, stop = 1 / plan.entry, 1 / plan.stop
    risk = stop - entry
    ratio1 = (plan.tp1 - plan.entry) / (plan.entry - plan.stop)
    ratio2 = (plan.tp2 - plan.entry) / (plan.entry - plan.stop)
    zone = (1 / plan.zone[1], 1 / plan.zone[0]) if plan.zone else None
    return Plan(plan.setup, entry, stop, entry - ratio1 * risk, entry - ratio2 * risk, zone, plan.trigger,
                plan.price_vs_zone, direction=-1)


def plan_lines(plans: list[Plan], common: Any, exits: Any, footer: str | list[str] | None = DEFAULT_FOOTER,
               trigger_label: str = "1H") -> list[str]:
    """Texto para a lista de motivos do painel."""
    if not plans:
        return ["Plano: nenhum setup aplicável agora (tendência e compressão abaixo do mínimo)"]
    lines = []
    for p in plans:
        short = p.direction < 0
        name = "Pullback" if p.setup == "pullback_tendencia" else "Rompimento"
        where = (f"zona de {'venda' if short else 'compra'} {fmt_price(p.zone[0])}–{fmt_price(p.zone[1])}" if p.zone
                 else f"entrada {fmt_price(p.entry)}")
        status = {
            "aguardando": " (aguardando o repique até a zona)" if short else " (aguardando o recuo até a zona)",
            "na_zona": " (preço já na zona)",
            "contra": (f" (preço acima da zona: precisa perder a EMA20 {trigger_label})" if short
                       else f" (preço abaixo da zona: precisa recuperar a EMA20 {trigger_label})"),
        }.get(p.price_vs_zone, "")
        stop_ok = common.min_stop_pct <= p.stop_pct <= common.max_stop_pct
        warn = "" if stop_ok else (f" — stop {_br(p.stop_pct, '.2f')}% fora da faixa {_br(common.min_stop_pct)}–"
                                   f"{_br(common.max_stop_pct)}%: o sinal seria barrado")
        lines.append(f"Plano {name}{' VENDA' if short else ''}: {where}{status}; gatilho: {p.trigger}; "
                     f"stop ~{fmt_price(p.stop)} ({_br(p.stop_pct, '.2f')}%); alvos {fmt_price(p.tp1)} "
                     f"({_br(exits.tp1_r)}R) / {fmt_price(p.tp2)} ({_br(exits.tp2_r)}R){warn}")
    if footer:
        lines.extend([footer] if isinstance(footer, str) else footer)
    return lines


SETUP_NAMES = {"pullback_tendencia": "Pullback", "rompimento_compressao": "Rompimento", "ote_fibo": "OTE"}


def plan_dict(p: Plan) -> dict[str, Any]:
    """Plano em números para o painel desenhar no gráfico (entrada, stop, alvos e zona)."""
    return {"setup": SETUP_NAMES.get(p.setup, p.setup), "lado": "venda" if p.direction < 0 else "compra",
            "entrada": p.entry, "stop": p.stop, "tp1": p.tp1, "tp2": p.tp2,
            "zona": list(p.zone) if p.zone else None, "stop_pct": round(p.stop_pct, 3),
            "situacao": p.price_vs_zone or None, "gatilho": p.trigger, "alerta": False}


def signal_dict(s: Any) -> dict[str, Any]:
    """Sinal que DISPAROU (alerta) no mesmo formato do plano, com alerta = True."""
    return {"setup": SETUP_NAMES.get(s.setup, s.setup), "lado": "venda" if s.direction < 0 else "compra",
            "entrada": s.entry, "stop": s.stop, "tp1": s.tp1, "tp2": s.tp2, "zona": None,
            "stop_pct": round(s.stop_pct, 3), "situacao": "disparou", "gatilho": "setup disparou no fechamento da vela",
            "alerta": True}
