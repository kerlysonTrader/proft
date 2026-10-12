"""Preços do MetaTrader 5 da corretora — SOMENTE LEITURA.

Usa o pacote oficial `MetaTrader5` ligado ao terminal que já está aberto no PC (Windows).
Só chama funções de leitura (initialize/shutdown, account_info, terminal_info, symbol_info,
symbol_info_tick, copy_rates_from_pos). Nunca envia ordens, nunca altera gráficos, EAs ou a
Observação do Mercado.

Horários: o MT5 devolve o horário do SERVIDOR (Doo = UTC+3) como se fosse epoch. Convertemos
para UTC subtraindo o fuso, medido pelo último tick (ou o do config, com o mercado fechado).
Velas diárias/4H ficam alinhadas à meia-noite do servidor (21:00 UTC); o backtest usa o
fechamento real de cada vela, então isso não muda nada além do recorte do dia.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from bot.bybit.client import KLINE_INTERVAL_MS, Kline
from bot.logging_setup import get_logger

log = get_logger("markets.mt5")

TIMEFRAME_NAMES = {"15": "TIMEFRAME_M15", "60": "TIMEFRAME_H1", "240": "TIMEFRAME_H4", "D": "TIMEFRAME_D1"}
FRESH_TICK_SECONDS = 15 * 60


class Mt5Error(Exception):
    pass


@dataclass(frozen=True)
class SymbolMeta:
    symbol: str
    digits: int
    point: float
    spread_points: int
    bid: float
    ask: float

    @property
    def spread_price(self) -> float:
        return self.spread_points * self.point

    def spread_pct(self, price: float | None = None) -> float:
        ref = price or (self.bid + self.ask) / 2 or 0.0
        return self.spread_price / ref * 100 if ref else float("nan")


class Mt5Reader:
    """Leitor de preços. Use com `with Mt5Reader(...) as mt5r:` para abrir/fechar a ligação."""

    def __init__(self, fallback_offset_hours: int = 3, max_bars: int = 100_000, api: Any = None,
                 clock=time.time) -> None:
        self.fallback_offset = fallback_offset_hours
        self.max_bars = max_bars
        self._api = api
        self._clock = clock
        self.offset_hours = fallback_offset_hours

    @property
    def api(self) -> Any:
        if self._api is None:
            import MetaTrader5  # só existe no Windows com o terminal instalado

            self._api = MetaTrader5
        return self._api

    def __enter__(self) -> Mt5Reader:
        if not self.api.initialize():
            raise Mt5Error(f"não foi possível ligar ao MT5 aberto: {self.api.last_error()}")
        return self

    def __exit__(self, *exc) -> None:
        self.api.shutdown()

    def describe(self) -> dict[str, Any]:
        acc, term = self.api.account_info(), self.api.terminal_info()
        return {"server": getattr(acc, "server", "?"), "company": getattr(acc, "company", "?"),
                "demo": getattr(acc, "trade_mode", None) == getattr(self.api, "ACCOUNT_TRADE_MODE_DEMO", 0),
                "connected": getattr(term, "connected", False), "maxbars": getattr(term, "maxbars", None)}

    def detect_offset(self, probe_symbols: list[str]) -> int:
        """Fuso do servidor pelo último tick recente; mercado fechado -> valor do config."""
        now = self._clock()
        for symbol in probe_symbols:
            tick = self.api.symbol_info_tick(symbol)
            if tick is None:
                continue
            offset = round((tick.time - now) / 3600)
            plausible = -12 <= offset <= 14  # tick antigo (mercado fechado) daria um "fuso" absurdo
            if plausible and abs(tick.time - offset * 3600 - now) <= FRESH_TICK_SECONDS:
                self.offset_hours = int(offset)
                return self.offset_hours
        log.warning("sem tick recente; usando o fuso do config", extra={"data": {"offset_h": self.fallback_offset}})
        self.offset_hours = self.fallback_offset
        return self.offset_hours

    def meta(self, symbol: str) -> SymbolMeta | None:
        info = self.api.symbol_info(symbol)
        if info is None:
            return None
        tick = self.api.symbol_info_tick(symbol)
        return SymbolMeta(symbol, int(info.digits), float(info.point), int(info.spread),
                          float(getattr(tick, "bid", 0.0) or 0.0), float(getattr(tick, "ask", 0.0) or 0.0))

    def rates(self, symbol: str, interval: str, count: int | None = None) -> list[Kline]:
        """As últimas `count` velas FECHADAS do símbolo, em ordem cronológica, horário UTC."""
        tf = getattr(self.api, TIMEFRAME_NAMES[interval])
        limit = self.max_bars - 1  # o terminal recusa exatamente "máx. barras" (Invalid params)
        count = min(count or limit, limit)
        data = self.api.copy_rates_from_pos(symbol, tf, 0, count)
        if data is None:
            raise Mt5Error(f"{symbol} {interval}: sem dados ({self.api.last_error()})")
        step = KLINE_INTERVAL_MS[interval]
        now_ms = int(self._clock() * 1000)
        shift = self.offset_hours * 3_600_000
        out = []
        for row in data:
            start = int(row["time"]) * 1000 - shift
            if start + step > now_ms:
                continue  # vela em formação
            close = float(row["close"])
            volume = float(row["tick_volume"])
            out.append(Kline(start, interval, float(row["open"]), float(row["high"]), float(row["low"]), close,
                             volume, volume * close, symbol))
        return out
