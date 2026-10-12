"""Mostra os indicadores da última vela FECHADA para conferir com o TradingView (Gate 2).

    python -m bot.tools.indicator_snapshot --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 240

No TradingView use o gráfico da própria Bybit (ex.: BYBIT:BTCUSDT, spot), o mesmo tempo
gráfico e passe o mouse sobre a vela indicada. Indicadores padrão do TradingView:
EMA (fonte close), RSI 14, ATR 14 (suavização RMA), DMI 14/14, MACD 12/26/9, BB 20/2.
Só usa dados públicos: roda no PC, sem chave.
"""

from __future__ import annotations

import argparse
import sys
from zoneinfo import ZoneInfo

from bot.bybit.client import BybitClient
from bot.config import load_config
from bot.data.market_data import MarketData
from bot.indicators import atr, bollinger, cmf, dmi, ema, macd, rsi
from bot.logging_setup import setup_logging

CANDLES = 1000  # histórico para o aquecimento da EMA200 convergir


def snapshot(md: MarketData, ind, symbol: str, interval: str) -> dict[str, float | str]:
    df = md.klines(symbol, interval, limit=CANDLES)
    close = df["close"]
    d = dmi(df, ind.adx_period)
    m = macd(close, ind.macd_fast, ind.macd_slow, ind.macd_signal)
    bb = bollinger(close, ind.bollinger_period, ind.bollinger_std)
    return {
        "time": df.index[-1],
        "candles": len(df),
        "close": close.iloc[-1],
        f"EMA{ind.ema_short}": ema(close, ind.ema_short).iloc[-1],
        f"EMA{ind.ema_mid}": ema(close, ind.ema_mid).iloc[-1],
        f"EMA{ind.ema_long}": ema(close, ind.ema_long).iloc[-1],
        f"RSI{ind.rsi_period}": rsi(close, ind.rsi_period).iloc[-1],
        f"ATR{ind.atr_period}": atr(df, ind.atr_period).iloc[-1],
        "ADX": d["adx"].iloc[-1],
        "DI+": d["plus_di"].iloc[-1],
        "DI-": d["minus_di"].iloc[-1],
        "MACD hist": m["hist"].iloc[-1],
        "BB largura": bb["width"].iloc[-1],
        f"CMF{ind.cmf_period}": cmf(df, ind.cmf_period).iloc[-1],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Indicadores da última vela fechada")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    parser.add_argument("--interval", default="240", help="60 = 1H, 240 = 4H, D = diário")
    args = parser.parse_args(argv)
    config = load_config()
    setup_logging("WARNING")
    client = BybitClient.from_config(config, secrets=None, mode="paper")
    client.sync_time()
    md = MarketData(client, config.market_data)
    tz = ZoneInfo(config.timezone)
    for symbol in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        snap = snapshot(md, config.indicators, symbol, args.interval)
        opened = snap.pop("time")
        print(f"\n{symbol} — vela {args.interval} aberta em {opened.astimezone(tz):%d/%m/%Y %H:%M} "
              f"(horário de {config.timezone}) / {opened:%H:%M} UTC — {snap.pop('candles')} velas de histórico")
        for name, value in snap.items():
            print(f"  {name:<12} {value:,.6f}" if abs(value) < 1 else f"  {name:<12} {value:,.4f}")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
