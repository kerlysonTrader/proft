"""Backtest do setup experimental bull_canal (Bull H1M1, modo contínuo) em velas de 15m.

Por moeda, o BullCycle percorre as velas de 15m e gera os sinais de COMPRA (vendas ficam virtuais).
A carteira usa as mesmas peças do robô: motor de risco (tamanho, tetos, bloqueios), Position
(SL/TP fixos do método; stop primeiro se os dois forem tocados na mesma vela), taxas e slippage.
Entrada: a mercado na abertura da vela seguinte ao sinal (+ slippage).

Filtros opcionais (variantes do experimento):
- `use_universe`: só moedas que estão no universo do robô naquela hora (liquidez/variação 24h);
- `use_regime`: só quando o regime do BTC permite novas entradas (≠ risk_off, sem circuit breaker).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pandas as pd

from bot.backtest.engine import Backtester, BacktestResult, SymbolData, TradeRecord
from bot.exits.position import Position, process_candle
from bot.risk.risk_manager import OpenExposure, RiskManager
from bot.signals.bull_canal import BullCycle

M15 = 15 * 60_000
H = 3_600_000
SETUP = "bull_canal"
BULL_EXITS = SimpleNamespace(tp1_close_fraction=1.0, move_stop_to_breakeven_after_tp1=False,
                             mode_after_tp1="fixed_tp2")


@dataclass
class BullParams:
    n_candles: int = 4
    min_channel_pct: float = 0.24
    stop_pct: float = 10.0
    filter_pct: float = 15.0
    cancel_break_pct: float = 50.0
    cancel_wait_pct: float = 50.0
    use_universe: bool = True
    use_regime: bool = True


def bull_buy_signals(df15: pd.DataFrame, p: BullParams) -> list:
    cycle = BullCycle(n_candles=p.n_candles, min_channel_pct=p.min_channel_pct, stop_pct=p.stop_pct,
                      filter_pct=p.filter_pct, cancel_break_pct=p.cancel_break_pct,
                      cancel_wait_pct=p.cancel_wait_pct, max_reversals=0, bar_ms=M15)
    for t, o, h, low, c in zip(df15["start_ms"].to_numpy(), df15["open"].to_numpy(), df15["high"].to_numpy(),
                               df15["low"].to_numpy(), df15["close"].to_numpy(), strict=True):
        cycle.feed(int(t), float(o), float(h), float(low), float(c))
    return [s for s in cycle.signals if s.direction > 0]


@dataclass
class HourContext:
    """Para cada fechamento de hora: regime permite entradas? quais moedas estão no universo?"""
    allow: dict[int, bool] = field(default_factory=dict)
    regime: dict[int, str] = field(default_factory=dict)
    universe: dict[int, set] = field(default_factory=dict)


def hour_context(config: Any, data1h: dict[str, SymbolData], start_ms: int, end_ms: int) -> HourContext:
    """Usa a mesma varredura do robô (Backtester._scan) hora a hora."""
    bt = Backtester(config, data1h, start_ms, end_ms)
    ctx = HourContext()
    for ts in (int(t) for t in bt.btc.h1["start_ms"].to_numpy() + H):
        if not start_ms - H <= ts <= end_ms:
            continue
        regime, scored = bt._scan(ts)
        ctx.allow[ts] = regime.allow_new_entries
        ctx.regime[ts] = regime.regime
        ctx.universe[ts] = {sym for sym, *_ in scored}
    return ctx


class BullBacktester:
    def __init__(self, config: Any, data15: dict[str, pd.DataFrame], start_ms: int, end_ms: int,
                 params: BullParams, ctx: HourContext | None, fees: dict[str, float] | None = None) -> None:
        self.cfg, self.data15, self.p, self.ctx = config, data15, params, ctx
        self.start_ms, self.end_ms = start_ms, end_ms
        self.fee = config.costs.fee_rate_per_side
        self.fees = fees or {}
        self.slip = config.costs.backtest_slippage_pct
        self.cash = config.backtest.initial_equity_usdt
        self.risk = RiskManager(config.risk, self.cash)
        self.positions: dict[str, Position] = {}
        self.pending: dict[str, Any] = {}   # símbolo -> (sinal, qty, regime) para entrar na próxima vela
        self.trades: list[TradeRecord] = []
        self.equity: dict[int, float] = {}
        self.blocks: Counter = Counter()
        self.counters = Counter()
        self.rows = {s: {int(t): i for i, t in enumerate(df["start_ms"].to_numpy())} for s, df in data15.items()}
        self.arrays = {s: {c: df[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close")}
                       for s, df in data15.items()}

    def _bar(self, sym: str, start: int):
        i = self.rows[sym].get(start)
        if i is None:
            return None
        a = self.arrays[sym]
        return a["open"][i], a["high"][i], a["low"][i], a["close"][i]

    def _hour_key(self, ts: int) -> int:
        return ts - ts % H  # última hora fechada até ts

    def _record(self, pos: Position) -> None:
        self.trades.append(TradeRecord(pos.symbol, SETUP, 0.0, pos.regime, pos.opened_ms, pos.closed_ms or 0,
                                       pos.entry, pos.exit_price, pos.qty, pos.pnl, pos.r_multiple, pos.fees,
                                       "stop" if pos.exit_reason == "stop" else "tp", False))
        self.risk.on_trade_closed(pos.pnl, pos.closed_ms or 0)

    def _equity(self, start: int) -> float:
        value = self.cash
        for sym, pos in self.positions.items():
            bar = self._bar(sym, start)
            value += pos.qty_open * (bar[3] if bar else pos.entry)
        return value

    def run(self) -> BacktestResult:
        signals = {}
        for sym, df in self.data15.items():
            for s in bull_buy_signals(df, self.p):
                if self.start_ms <= s.t <= self.end_ms:
                    signals.setdefault(s.t, []).append((sym, s))
        grid = sorted({int(t) for df in self.data15.values() for t in df["start_ms"].to_numpy()
                       if self.start_ms <= t <= self.end_ms})
        for start in grid:
            end = start + M15
            # 1) entradas pendentes: a mercado na abertura desta vela
            for sym, (sig, qty, regime) in list(self.pending.items()):
                bar = self._bar(sym, start)
                if bar is None:
                    continue
                del self.pending[sym]
                o, h, low, _ = bar
                price = o * (1 + self.slip / 100)
                fee = self.fees.get(sym, self.fee)
                if price <= sig.sl or price >= sig.tp:
                    self.counters["entrada desistida (abriu além do stop/alvo)"] += 1
                    continue
                cost = qty * price * (1 + fee)
                if cost > self.cash:
                    qty = self.cash / (price * (1 + fee))
                    cost = self.cash
                if qty * price < self.cfg.risk.min_order_notional_usdt:
                    continue
                self.cash -= cost
                pos = Position(sym, SETUP, price, qty, sig.sl, sig.tp, sig.tp, end, fee_rate=fee, regime=regime)
                self.positions[sym] = pos
                fills = process_candle(pos, price, h, low, end, BULL_EXITS, self.slip)
                self._close_fills(pos, fills)
            # 2) posições abertas antes desta vela
            for sym, pos in list(self.positions.items()):
                if pos.opened_ms == end:
                    continue
                bar = self._bar(sym, start)
                if bar is None:
                    continue
                o, h, low, _ = bar
                self._close_fills(pos, process_candle(pos, o, h, low, end, BULL_EXITS, self.slip))
            equity = self._equity(start)
            self.risk.mark(equity, end)
            self.equity[end] = equity
            # 3) sinais desta vela (fechou agora) -> entrada na próxima
            for sym, sig in signals.get(start, []):
                self.counters["sinais"] += 1
                hk = self._hour_key(end)
                regime = self.ctx.regime.get(hk, "?") if self.ctx else "?"
                if self.ctx and self.p.use_regime and not self.ctx.allow.get(hk, False):
                    self.blocks["regime não permite entradas"] += 1
                    continue
                if self.ctx and self.p.use_universe and sym not in self.ctx.universe.get(hk, set()):
                    self.blocks["fora do universo (liquidez/variação)"] += 1
                    continue
                if sym in self.positions or sym in self.pending:
                    self.blocks["já há posição/ordem"] += 1
                    continue
                entry_ref = self._bar(sym, start)[3]
                exposures = [OpenExposure(s, p.qty_open * p.entry) for s, p in self.positions.items()]
                exposures += [OpenExposure(s, q * sg.line) for s, (sg, q, _) in self.pending.items()]
                decision = self.risk.size(symbol=sym, base=sym, entry=entry_ref, stop=sig.sl, equity=equity,
                                          free_cash=self.cash, exposures=exposures,
                                          regime=regime if regime != "?" else "risk_on", now_ms=end)
                if not decision.ok:
                    self.blocks[decision.reasons[0].split(":")[0][:60]] += 1
                    continue
                self.pending[sym] = (sig, decision.qty, regime)
                self.counters["ordens"] += 1
        last = grid[-1] + M15 if grid else self.end_ms
        for sym, pos in list(self.positions.items()):
            close = self._bar(sym, grid[-1])
            pos._exit(pos.qty_open, close[3] if close else pos.entry, "fim_do_teste", last)
            self._close_fills(pos, pos.fills[-1:])
        self.equity[last] = self.cash
        return BacktestResult(
            start_ms=grid[0] if grid else self.start_ms, end_ms=last,
            initial_equity=self.cfg.backtest.initial_equity_usdt, trades=self.trades,
            equity=pd.Series(self.equity).sort_index(), risk_events=list(self.risk.state.events),
            signals_seen=self.counters["sinais"], signals_filtered=sum(self.blocks.values()),
            orders_placed=self.counters["ordens"], orders_expired=0, block_reasons=self.blocks,
            notes=["Bull H1M1 modo contínuo em velas de 15m (porte idêntico à referência validada)",
                   "Só compras; vendas viram trades virtuais; sem virada de mão (spot)",
                   f"Canal mínimo {self.p.min_channel_pct}% do preço; stop {self.p.stop_pct}% de H; alvo 1×H",
                   f"Filtros: universo={self.p.use_universe}, regime={self.p.use_regime}",
                   "Entrada a mercado na abertura da vela seguinte ao sinal (+ slippage)",
                   "Stop/alvo na mesma vela: considera o stop (conservador)"],
        )

    def _close_fills(self, pos: Position, fills) -> None:
        for f in fills:
            self.cash += f.qty * f.price * (1 - pos.fee_rate)
        if pos.closed and pos.symbol in self.positions:
            del self.positions[pos.symbol]
            self._record(pos)
