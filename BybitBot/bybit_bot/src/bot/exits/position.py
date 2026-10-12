"""Posição e regras de saída (seção 7 do 03_ESTRATEGIA.md).

Usado pelo backtest e pelo broker simulado (paper); no real, as mesmas decisões viram ordens
(stop no servidor da Bybit, venda parcial no TP1, ajuste do stop).

Dentro da vela (simulação), de forma CONSERVADORA:
- se a mínima toca o stop, sai pelo stop (ou pela abertura, se abriu abaixo), mesmo que a
  máxima tenha tocado o alvo na mesma vela;
- TP1 vende `tp1_close_fraction` e sobe o stop para entrada + taxas; se a mesma vela também
  descer até o novo stop, o restante sai no breakeven;
- modo fixed_tp2: o restante sai no TP2.
No fechamento da vela 1H: trailing (máx(stop, mínima das N últimas velas − buffer × ATR)),
stop de tempo (sem +min_r em N horas) e invalidação (fechamento 4H abaixo da EMA50 4H).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HOUR_MS = 3_600_000


@dataclass(frozen=True)
class ExitFill:
    qty: float
    price: float
    reason: str          # stop | breakeven | trailing | tp1 | tp2 | tempo | invalidacao
    ts_ms: int


@dataclass
class Position:
    symbol: str
    setup: str
    entry: float
    qty: float                   # quantidade inicial
    stop: float
    tp1: float
    tp2: float
    opened_ms: int
    order_link_id: str = ""
    score: float = 0.0
    regime: str = ""
    fee_rate: float = 0.001
    initial_stop: float = 0.0
    qty_open: float = 0.0
    tp1_hit: bool = False
    stop_kind: str = "stop"      # o que o stop atual representa
    max_high: float = 0.0
    fills: list[ExitFill] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.initial_stop = self.initial_stop or self.stop
        self.qty_open = self.qty_open or self.qty
        self.max_high = self.max_high or self.entry

    @property
    def risk_per_unit(self) -> float:
        return self.entry - self.initial_stop

    @property
    def closed(self) -> bool:
        return self.qty_open <= 1e-12

    @property
    def breakeven(self) -> float:
        """Entrada + taxas de entrada e saída."""
        return self.entry * (1 + 2 * self.fee_rate)

    def r_at(self, price: float) -> float:
        return (price - self.entry) / self.risk_per_unit if self.risk_per_unit > 0 else 0.0

    def _exit(self, qty: float, price: float, reason: str, ts_ms: int) -> ExitFill:
        qty = min(qty, self.qty_open)
        fill = ExitFill(qty, price, reason, ts_ms)
        self.fills.append(fill)
        self.qty_open -= qty
        return fill

    # ------------------------------------------------------------------ resultado
    @property
    def exit_price(self) -> float:
        sold = sum(f.qty for f in self.fills)
        return sum(f.qty * f.price for f in self.fills) / sold if sold else float("nan")

    @property
    def fees(self) -> float:
        return self.fee_rate * (self.entry * self.qty + sum(f.qty * f.price for f in self.fills))

    @property
    def pnl(self) -> float:
        return sum((f.price - self.entry) * f.qty for f in self.fills) - self.fees

    @property
    def r_multiple(self) -> float:
        risk = self.risk_per_unit * self.qty
        return self.pnl / risk if risk > 0 else 0.0

    @property
    def exit_reason(self) -> str:
        return self.fills[-1].reason if self.fills else ""

    @property
    def closed_ms(self) -> int | None:
        return self.fills[-1].ts_ms if self.closed and self.fills else None


def process_candle(pos: Position, o: float, h: float, low: float, ts_ms: int, exits: Any,
                   slippage_pct: float) -> list[ExitFill]:
    """Stop/alvos tocados dentro da vela (ts_ms = fechamento da vela). Ordem conservadora."""
    out: list[ExitFill] = []
    slip = 1 - slippage_pct / 100
    if low <= pos.stop:
        out.append(pos._exit(pos.qty_open, min(pos.stop, o) * slip, pos.stop_kind, ts_ms))
        return out
    if not pos.tp1_hit and h >= pos.tp1:
        out.append(pos._exit(pos.qty * exits.tp1_close_fraction, max(pos.tp1, o), "tp1", ts_ms))
        pos.tp1_hit = True
        if exits.move_stop_to_breakeven_after_tp1 and pos.breakeven > pos.stop:
            pos.stop, pos.stop_kind = pos.breakeven, "breakeven"
        if low <= pos.stop:  # a mesma vela voltou até o novo stop: o restante sai nele
            out.append(pos._exit(pos.qty_open, pos.stop * slip, pos.stop_kind, ts_ms))
            return out
    if pos.tp1_hit and exits.mode_after_tp1 == "fixed_tp2" and h >= pos.tp2:
        out.append(pos._exit(pos.qty_open, max(pos.tp2, o), "tp2", ts_ms))
    pos.max_high = max(pos.max_high, h)
    return out


def on_candle_close(pos: Position, *, close: float, recent_lows: list[float], atr_1h: float, ts_ms: int,
                    exits: Any, slippage_pct: float, close_4h_below_ema50: bool = False,
                    regime_risk_off: bool = False) -> ExitFill | None:
    """Regras avaliadas no fechamento da vela 1H. Pode mover o stop ou encerrar a posição."""
    if pos.closed:
        return None
    slip = 1 - slippage_pct / 100
    if exits.invalidation_close_below_ema50_4h and close_4h_below_ema50:
        return pos._exit(pos.qty_open, close * slip, "invalidacao", ts_ms)
    hours = (ts_ms - pos.opened_ms) / HOUR_MS
    if hours >= exits.time_stop_hours and pos.r_at(pos.max_high) < exits.time_stop_min_r:
        return pos._exit(pos.qty_open, close * slip, "tempo", ts_ms)
    if pos.tp1_hit and exits.mode_after_tp1 == "trailing" and recent_lows and atr_1h == atr_1h:
        candidate = min(recent_lows[-exits.trailing_lookback_candles_1h:]) - exits.trailing_atr_buffer * atr_1h
        if candidate > pos.stop and candidate < close:
            pos.stop, pos.stop_kind = candidate, "trailing"
    if regime_risk_off and close > pos.breakeven > pos.stop:
        pos.stop, pos.stop_kind = pos.breakeven, "breakeven"
    return None
