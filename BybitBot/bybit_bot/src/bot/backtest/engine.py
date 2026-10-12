"""Backtest orientado a eventos (Fase 5) com o MESMO código do robô.

A cada hora T (fechamento de uma vela 1H), nesta ordem:
1. Ordens limite pendentes: preenchem se a mínima da vela tocar o preço (no preço limite, ou na
   abertura se abriu abaixo); expiram ao fim da validade. Se a mesma vela também tocar o stop,
   a posição sai no stop (conservador).
2. Posições: stop/TP1/TP2 dentro da vela (process_candle; stop primeiro em caso de dúvida).
3. Patrimônio marcado no fechamento; motor de risco atualiza pico, dia, semana e bloqueios.
4. Regras de fechamento: invalidação 4H, stop de tempo, trailing, breakeven em risk_off.
5. Varredura: universo (liquidez e variação 24h pelas velas 1H), regime do BTC (evaluate_regime),
   score (score_features) e Watchlist A.
6. Gatilhos na Watchlist A (pullback/breakout/ote com velas até T), filtros comuns, tamanho pelo
   motor de risco -> ordem limite pendente.

Limitações registradas no relatório: Gemini desligado; sem histórico de derivativos (pontuação
neutra para todos); spread e profundidade não simulados (sem histórico do livro); universo =
moedas grandes de hoje (viés de sobrevivência).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from bot.data.market_data import klines_to_frame
from bot.exits.position import Position, on_candle_close, process_candle
from bot.indicators import atr
from bot.logging_setup import get_logger
from bot.risk.risk_manager import OpenExposure, RiskManager
from bot.scanner.features import FEATURE_COLUMNS, Features, feature_frame
from bot.scanner.regime import RegimeState, breadth_pct, evaluate_regime
from bot.scanner.scoring import classify, score_features
from bot.signals.engine import evaluate_setups
from bot.signals.filters import SignalContext, check_filters
from bot.storage.kline_store import KlineStore

log = get_logger("backtest.engine")
H = 3_600_000
H4 = 4 * H
STOP_REASONS = {"stop"}


@dataclass
class SymbolData:
    symbol: str
    base: str
    h1: pd.DataFrame
    h4: pd.DataFrame
    d1: pd.DataFrame
    features: np.ndarray            # linhas = velas 1H, colunas = FEATURE_COLUMNS + turnover_24h
    columns: list[str]
    hour_pos: dict[int, int]        # fechamento da vela 1H (ms) -> posição
    h4_ends: np.ndarray
    d1_ends: np.ndarray
    atr_1h: np.ndarray

    def features_at(self, i: int) -> Features:
        values = dict(zip(self.columns, self.features[i], strict=True))
        values.pop("turnover_24h", None)
        values["daily_candles"] = int(values["daily_candles"])
        return Features(symbol=self.symbol, **values)

    def value(self, i: int, column: str) -> float:
        return float(self.features[i, self.columns.index(column)])


@dataclass
class PendingOrder:
    signal: Any
    qty: float
    notional: float
    regime: str
    base: str
    placed_ms: int


@dataclass
class TradeRecord:
    symbol: str
    setup: str
    score: float
    regime: str
    opened_ms: int
    closed_ms: int
    entry: float
    exit_price: float
    qty: float
    pnl: float
    r: float
    fees: float
    exit_reason: str
    tp1_hit: bool


@dataclass
class BacktestResult:
    start_ms: int
    end_ms: int
    initial_equity: float
    trades: list[TradeRecord]
    equity: pd.Series                 # patrimônio por hora (índice = ms)
    risk_events: list[str]
    signals_seen: int = 0
    signals_filtered: int = 0
    orders_placed: int = 0
    orders_expired: int = 0
    notes: list[str] = field(default_factory=list)


def load_symbol(store: KlineStore, symbol: str, base: str, btc_d1: pd.DataFrame | None, config: Any
                ) -> SymbolData | None:
    h1 = klines_to_frame(store.load(symbol, "60"))
    h4 = klines_to_frame(store.load(symbol, "240"))
    d1 = klines_to_frame(store.load(symbol, "D"))
    if len(h1) < 200 or len(h4) < 50 or len(d1) < 30:
        return None
    btc = d1 if btc_d1 is None else btc_d1
    frame = feature_frame(d1, h4, h1, btc, config.indicators, config.score)
    columns = [*FEATURE_COLUMNS, "turnover_24h"]
    frame = frame.reindex(columns=columns)
    ends = (h1["start_ms"].to_numpy() + H).tolist()
    return SymbolData(
        symbol=symbol, base=base, h1=h1, h4=h4, d1=d1,
        features=frame.to_numpy(dtype=float), columns=columns,
        hour_pos={int(t): i for i, t in enumerate(ends)},
        h4_ends=h4["start_ms"].to_numpy() + H4,
        d1_ends=d1["start_ms"].to_numpy() + 24 * H,
        atr_1h=atr(h1, config.indicators.atr_period).to_numpy(),
    )


class Backtester:
    def __init__(self, config: Any, data: dict[str, SymbolData], start_ms: int, end_ms: int,
                 progress: Callable[[int, int], None] | None = None) -> None:
        self.cfg = config
        self.data = data
        self.btc = data[config.regime.btc_symbol]
        self.start_ms, self.end_ms = start_ms, end_ms
        self.progress = progress
        bt = config.backtest
        self.cash = bt.initial_equity_usdt
        self.reserved = 0.0
        self.risk = RiskManager(config.risk, bt.initial_equity_usdt)
        self.regime_state = RegimeState()
        self.positions: dict[str, Position] = {}
        self.pending: dict[str, PendingOrder] = {}
        self.last_stop_ms: dict[str, int] = {}
        self.trades: list[TradeRecord] = []
        self.equity: dict[int, float] = {}
        self.counters = {"signals": 0, "filtered": 0, "placed": 0, "expired": 0}
        self.fee = config.costs.fee_rate_per_side
        self.slip = config.costs.backtest_slippage_pct

    # ------------------------------------------------------------------ helpers
    def _row(self, sd: SymbolData, ts: int) -> int | None:
        return sd.hour_pos.get(ts)

    def _close_at(self, sd: SymbolData, ts: int) -> float | None:
        i = self._row(sd, ts)
        return float(sd.h1["close"].iat[i]) if i is not None else None

    def _equity(self, ts: int) -> float:
        value = self.cash + self.reserved
        for sym, pos in self.positions.items():
            price = self._close_at(self.data[sym], ts)
            value += pos.qty_open * (price if price is not None else pos.entry)
        return value

    def _slice(self, df: pd.DataFrame, ends: np.ndarray, ts: int, n: int) -> pd.DataFrame:
        k = int(np.searchsorted(ends, ts, side="right"))  # velas com fechamento <= ts
        return df.iloc[max(0, k - n):k]

    def _record(self, pos: Position) -> None:
        self.trades.append(TradeRecord(
            symbol=pos.symbol, setup=pos.setup, score=pos.score, regime=pos.regime, opened_ms=pos.opened_ms,
            closed_ms=pos.closed_ms or 0, entry=pos.entry, exit_price=pos.exit_price, qty=pos.qty, pnl=pos.pnl,
            r=pos.r_multiple, fees=pos.fees, exit_reason=pos.exit_reason, tp1_hit=pos.tp1_hit))
        self.risk.on_trade_closed(pos.pnl, pos.closed_ms or 0)
        if pos.exit_reason in STOP_REASONS:
            self.last_stop_ms[pos.symbol] = pos.closed_ms or 0

    def _apply_fills(self, pos: Position, fills) -> None:
        for f in fills:
            self.cash += f.qty * f.price * (1 - self.fee)
        if pos.closed:
            del self.positions[pos.symbol]
            self._record(pos)

    # ------------------------------------------------------------------ passos
    def _process_orders(self, ts: int) -> None:
        for sym, order in list(self.pending.items()):
            sd = self.data[sym]
            i = self._row(sd, ts)
            s = order.signal
            if i is not None and ts > order.placed_ms:
                o, h, low = (float(sd.h1[c].iat[i]) for c in ("open", "high", "low"))
                if low <= s.entry:
                    price = min(s.entry, o)
                    qty = order.notional / s.entry  # o caixa reservado define a quantidade
                    self.reserved -= order.notional
                    self.cash += order.notional - qty * price * (1 + self.fee)
                    del self.pending[sym]
                    pos = Position(sym, s.setup, price, qty, s.stop, s.tp1, s.tp2, ts, s.order_link_id, s.score,
                                   order.regime, self.fee)
                    self.positions[sym] = pos
                    if low <= pos.stop:  # mesma vela tocou o stop: conservador
                        self._apply_fills(pos, [pos._exit(pos.qty_open, pos.stop * (1 - self.slip / 100),
                                                          "stop", ts)])
                    continue
            if ts >= s.valid_until_ms:
                self.reserved -= order.notional
                self.cash += order.notional
                del self.pending[sym]
                self.counters["expired"] += 1

    def _process_positions(self, ts: int) -> None:
        for sym, pos in list(self.positions.items()):
            if pos.opened_ms == ts:
                continue  # preenchida nesta vela: já checada
            sd = self.data[sym]
            i = self._row(sd, ts)
            if i is None:
                continue
            o, h, low = (float(sd.h1[c].iat[i]) for c in ("open", "high", "low"))
            self._apply_fills(pos, process_candle(pos, o, h, low, ts, self.cfg.exits, self.slip))

    def _close_rules(self, ts: int, risk_off: bool) -> None:
        for sym, pos in list(self.positions.items()):
            sd = self.data[sym]
            i = self._row(sd, ts)
            if i is None:
                continue
            close = float(sd.h1["close"].iat[i])
            lows = sd.h1["low"].iloc[max(0, i - 9):i + 1].tolist()
            below_ema = False
            if ts % H4 == 0:
                c4, e50 = sd.value(i, "close_4h"), sd.value(i, "ema50_4h")
                below_ema = bool(c4 < e50) if not (np.isnan(c4) or np.isnan(e50)) else False
            fill = on_candle_close(pos, close=close, recent_lows=lows, atr_1h=float(sd.atr_1h[i]), ts_ms=ts,
                                   exits=self.cfg.exits, slippage_pct=self.slip, close_4h_below_ema50=below_ema,
                                   regime_risk_off=risk_off)
            if fill:
                self._apply_fills(pos, [fill])

    def _scan(self, ts: int):
        cfg, sc, u = self.cfg, self.cfg.score, self.cfg.universe
        btc_sym = cfg.regime.btc_symbol
        coins = []
        for sym, sd in self.data.items():
            i = self._row(sd, ts)
            if i is None:
                continue
            f = sd.features_at(i)
            turnover = sd.value(i, "turnover_24h")
            if sym != btc_sym:
                if f.daily_candles < u.min_daily_candles or np.isnan(turnover) or turnover < u.min_turnover_24h_usdt:
                    continue
                if np.isnan(f.change_24h_pct) or not u.min_change_24h_pct <= f.change_24h_pct <= u.max_change_24h_pct:
                    continue
            coins.append((sym, i, f))
        above = [f.close_4h > f.ema50_4h for _, _, f in coins if not (np.isnan(f.close_4h) or np.isnan(f.ema50_4h))]
        b = self.btc
        bt = cfg.backtest.candles
        regime = evaluate_regime(self._slice(b.d1, b.d1_ends, ts, bt.d1_btc), self._slice(b.h4, b.h4_ends, ts, bt.h4),
                                 self._slice(b.h1, b.h1["start_ms"].to_numpy() + H, ts, 200), breadth_pct(above),
                                 self.regime_state, ts, cfg.regime)
        scored = []
        for sym, i, f in coins:
            s = score_features(f, sc)
            scored.append((sym, i, s, classify(s.total, sc, regime.regime)))
        return regime, scored

    def _triggers(self, ts: int, regime, scored) -> None:
        cfg = self.cfg
        equity = self._equity(ts)
        for sym, _i, score, watchlist in sorted(scored, key=lambda x: -x[2].total):
            if watchlist != "A" or sym in self.positions or sym in self.pending:
                continue
            sd = self.data[sym]
            h1 = self._slice(sd.h1, sd.h1["start_ms"].to_numpy() + H, ts, cfg.backtest.candles.h1)
            h4 = self._slice(sd.h4, sd.h4_ends, ts, cfg.backtest.candles.h4)
            signals = evaluate_setups(sym, h1, h4, ts, score.components, score.total, cfg)
            if not signals:
                continue
            self.counters["signals"] += len(signals)
            ctx = SignalContext(now_ms=ts, allow_new_entries=regime.allow_new_entries, regime=regime.regime,
                                spread_pct={sym: 0.0}, open_symbols=set(self.positions) | set(self.pending),
                                last_stop_ms=self.last_stop_ms)
            for signal in signals:
                if check_filters(signal, ctx, cfg.setups.common, cfg.universe.max_spread_pct):
                    self.counters["filtered"] += 1
                    continue
                sectors = cfg.risk.sectors
                exposures = [OpenExposure(p.symbol, p.qty_open * p.entry, sectors.get(self.data[p.symbol].base))
                             for p in self.positions.values()]
                exposures += [OpenExposure(o.signal.symbol, o.notional, cfg.risk.sectors.get(o.base))
                              for o in self.pending.values()]
                decision = self.risk.size(symbol=sym, base=sd.base, entry=signal.entry, stop=signal.stop,
                                          equity=equity, free_cash=self.cash, exposures=exposures,
                                          regime=regime.regime, now_ms=ts)
                if not decision.ok:
                    self.counters["filtered"] += 1
                    continue
                self.cash -= decision.notional
                self.reserved += decision.notional
                self.pending[sym] = PendingOrder(signal, decision.qty, decision.notional, regime.regime, sd.base, ts)
                self.counters["placed"] += 1
                break  # um sinal por moeda

    # ------------------------------------------------------------------ loop
    def run(self) -> BacktestResult:
        hours = [int(t) for t in self.btc.h1["start_ms"].to_numpy() + H if self.start_ms <= t <= self.end_ms]
        for n, ts in enumerate(hours):
            self._process_orders(ts)
            self._process_positions(ts)
            regime, scored = self._scan(ts)
            equity = self._equity(ts)
            self.risk.mark(equity, ts)
            self._close_rules(ts, regime.regime == "risk_off")
            self._triggers(ts, regime, scored)
            self.equity[ts] = self._equity(ts)
            if self.progress and n % 500 == 0:
                self.progress(n, len(hours))
        last = hours[-1] if hours else self.end_ms
        for sym, pos in list(self.positions.items()):  # encerra o que sobrou no último fechamento
            price = self._close_at(self.data[sym], last) or pos.entry
            self._apply_fills(pos, [pos._exit(pos.qty_open, price, "fim_do_teste", last)])
        for order in self.pending.values():
            self.cash += order.notional
        self.reserved = 0.0
        if hours:
            self.equity[last] = self.cash
        return BacktestResult(
            start_ms=hours[0] if hours else self.start_ms, end_ms=last,
            initial_equity=self.cfg.backtest.initial_equity_usdt, trades=self.trades,
            equity=pd.Series(self.equity).sort_index(), risk_events=list(self.risk.state.events),
            signals_seen=self.counters["signals"], signals_filtered=self.counters["filtered"],
            orders_placed=self.counters["placed"], orders_expired=self.counters["expired"],
            notes=["Gemini desligado no backtest (veto qualitativo não simulado)",
                   "Sem histórico de derivativos: componente de derivativos com pontuação neutra para todas",
                   "Spread e profundidade do livro não simulados (sem histórico)",
                   "Universo = maiores moedas de hoje (viés de sobrevivência)",
                   "Stop/alvo na mesma vela: considera o stop (conservador)"],
        )
