"""Motor de risco (seção 6 do 03_ESTRATEGIA.md). Tem a palavra final sobre qualquer entrada.

- Tamanho: (patrimônio × risco %) ÷ (entrada − stop), reduzido pelos tetos de exposição e pelo
  caixa livre (spot, sem alavancagem); arredondado para baixo; abaixo do mínimo = não entra.
- Risco % = risk_per_trade_pct × fator do regime neutro × fator de cautela (Gemini).
- Bloqueios: kill switch (drawdown desde o pico), pausa por drawdown semanal (até a próxima
  segunda 00:00 UTC — no robô real, até revisão manual), perda diária (até 00:00 UTC),
  N stops seguidos (pausa de X horas), limite de posições (por regime) e por setor.
O estado é serializável (dict) para sobreviver a reinícios.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

HOUR_MS = 3_600_000


def _utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _next_midnight_ms(ms: int) -> int:
    d = _utc(ms)
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000) + 24 * HOUR_MS


def _next_monday_ms(ms: int) -> int:
    d = _utc(ms)
    start = datetime(d.year, d.month, d.day, tzinfo=UTC) - timedelta(days=d.weekday())
    return int((start + timedelta(days=7)).timestamp() * 1000)


@dataclass
class OpenExposure:
    symbol: str
    notional: float          # valor em USDT (posição aberta ou ordem pendente)
    sector: str | None = None


@dataclass
class RiskState:
    peak_equity: float
    day_key: str = ""
    day_start_equity: float = 0.0
    week_key: str = ""
    week_start_equity: float = 0.0
    consecutive_losses: int = 0
    pause_until_ms: int = 0
    weekly_pause_until_ms: int = 0
    kill_switch: bool = False
    kill_reason: str = ""
    events: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SizeDecision:
    qty: float
    notional: float
    risk_pct: float
    risk_usdt: float
    reasons: tuple[str, ...]        # bloqueios (qty = 0) ou ajustes aplicados

    @property
    def ok(self) -> bool:
        return self.qty > 0


class RiskManager:
    def __init__(self, risk_cfg: Any, initial_equity: float, state: RiskState | None = None) -> None:
        self.cfg = risk_cfg
        self.state = state or RiskState(peak_equity=initial_equity)

    # ------------------------------------------------------------------ marcação
    def mark(self, equity: float, now_ms: int) -> None:
        """Atualiza pico, dia, semana e os bloqueios por drawdown. Chamar a cada fechamento de vela."""
        s, c = self.state, self.cfg
        d = _utc(now_ms)
        day_key, week_key = d.strftime("%Y-%m-%d"), f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        if s.day_key != day_key:
            s.day_key, s.day_start_equity = day_key, equity
        if s.week_key != week_key:
            s.week_key, s.week_start_equity = week_key, equity
        s.peak_equity = max(s.peak_equity, equity)

        drawdown = (1 - equity / s.peak_equity) * 100 if s.peak_equity > 0 else 0.0
        if not s.kill_switch and drawdown >= c.max_drawdown_from_peak_pct:
            s.kill_switch = True
            s.kill_reason = f"drawdown de {drawdown:.1f}% desde o pico (limite {c.max_drawdown_from_peak_pct:g}%)"
            s.events.append(f"{d:%Y-%m-%d %H:%M} KILL SWITCH: {s.kill_reason}")
        weekly = (1 - equity / s.week_start_equity) * 100 if s.week_start_equity > 0 else 0.0
        if weekly >= c.weekly_drawdown_limit_pct and now_ms >= s.weekly_pause_until_ms:
            s.weekly_pause_until_ms = _next_monday_ms(now_ms)
            s.events.append(f"{d:%Y-%m-%d %H:%M} pausa semanal: drawdown {weekly:.1f}% na semana")

    def on_trade_closed(self, pnl_usdt: float, now_ms: int) -> None:
        s, c = self.state, self.cfg
        if pnl_usdt < 0:
            s.consecutive_losses += 1
            if s.consecutive_losses >= c.max_consecutive_losses:
                s.pause_until_ms = max(s.pause_until_ms, now_ms + int(c.consecutive_losses_pause_hours * HOUR_MS))
                s.events.append(f"{_utc(now_ms):%Y-%m-%d %H:%M} pausa: {s.consecutive_losses} perdas seguidas")
                s.consecutive_losses = 0
        else:
            s.consecutive_losses = 0

    # ------------------------------------------------------------------ bloqueios
    def block_reasons(self, equity: float, now_ms: int) -> list[str]:
        s, c = self.state, self.cfg
        reasons = []
        if s.kill_switch:
            reasons.append(f"kill switch: {s.kill_reason}")
        if now_ms < s.weekly_pause_until_ms:
            reasons.append("pausa por drawdown semanal")
        if now_ms < s.pause_until_ms:
            reasons.append("pausa após perdas seguidas")
        if s.day_start_equity > 0:
            daily = (1 - equity / s.day_start_equity) * 100
            if daily >= c.daily_loss_limit_pct:
                reasons.append(f"perda do dia {daily:.1f}% ≥ {c.daily_loss_limit_pct:g}% (até 00:00 UTC)")
        return reasons

    # ------------------------------------------------------------------ tamanho
    def size(
        self,
        *,
        symbol: str,
        base: str,
        entry: float,
        stop: float,
        equity: float,
        free_cash: float,
        exposures: list[OpenExposure],
        regime: str,
        now_ms: int,
        caution: bool = False,
        rules: Any = None,       # InstrumentRules (arredonda e valida) ou None (backtest)
    ) -> SizeDecision:
        c = self.cfg
        blocks = self.block_reasons(equity, now_ms)
        max_positions = c.max_open_positions_neutral if regime == "neutro" else c.max_open_positions
        if regime == "risk_off":
            blocks.append("regime risk_off")
        if len(exposures) >= max_positions:
            blocks.append(f"limite de {max_positions} posições/ordens no regime {regime}")
        if any(e.symbol == symbol for e in exposures):
            blocks.append("já há posição ou ordem nesta moeda")
        sector = c.sectors.get(base.upper())
        if sector and sum(e.sector == sector for e in exposures) >= c.max_positions_per_sector:
            blocks.append(f"limite de {c.max_positions_per_sector} posições no setor {sector}")
        risk_per_unit = entry - stop
        if risk_per_unit <= 0:
            blocks.append("stop acima da entrada")
        if blocks:
            return SizeDecision(0.0, 0.0, 0.0, 0.0, tuple(blocks))

        factor = (c.neutral_regime_risk_factor if regime == "neutro" else 1.0) * \
                 (c.caution_risk_factor if caution else 1.0)
        risk_pct = c.risk_per_trade_pct * factor
        qty = equity * risk_pct / 100 / risk_per_unit
        notes = []
        caps = {
            "exposição por moeda": equity * c.max_exposure_per_coin_pct / 100,
            "exposição total": equity * c.max_total_exposure_pct / 100 - sum(e.notional for e in exposures),
            "caixa livre": free_cash,
        }
        for name, cap in caps.items():
            if qty * entry > cap:
                qty = max(cap, 0.0) / entry
                notes.append(f"tamanho reduzido pelo teto de {name}")
        if rules is not None:
            from bot.bybit.instruments import OrderValidationError

            try:
                qty_d, _ = rules.validate_order(qty, entry)
                qty = float(qty_d)
            except OrderValidationError as exc:
                return SizeDecision(0.0, 0.0, risk_pct, 0.0, (*notes, f"não cabe nas regras do par: {exc}"))
        notional = qty * entry
        if notional < c.min_order_notional_usdt:
            return SizeDecision(0.0, 0.0, risk_pct, 0.0,
                                (*notes, f"valor {notional:.2f} USDT abaixo do mínimo {c.min_order_notional_usdt:g}"))
        return SizeDecision(qty, notional, risk_pct, qty * risk_per_unit, tuple(notes))
