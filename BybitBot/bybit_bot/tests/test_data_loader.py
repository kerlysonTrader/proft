from __future__ import annotations

from bot.backtest.data_loader import select_top_symbols
from bot.bybit.instruments import InstrumentRegistry, InstrumentRules
from bot.config import load_config
from conftest import CONFIG_PATH


def rules(symbol: str, base: str, status: str = "Trading") -> InstrumentRules:
    return InstrumentRules.from_api({
        "symbol": symbol, "baseCoin": base, "quoteCoin": "USDT", "status": status,
        "lotSizeFilter": {"basePrecision": "0.01", "minOrderQty": "0.01", "minOrderAmt": "1"},
        "priceFilter": {"tickSize": "0.01"},
    })


def test_seleciona_maiores_sem_stable_alavancado_e_lista_negra():
    universe = load_config(CONFIG_PATH).universe.model_copy(update={"blacklist": ["SCAM"]})
    registry = InstrumentRegistry({r.symbol: r for r in [
        rules("BTCUSDT", "BTC"), rules("ETHUSDT", "ETH"), rules("SOLUSDT", "SOL"),
        rules("USDCUSDT", "USDC"), rules("BTC3LUSDT", "BTC3L"), rules("SCAMUSDT", "SCAM"),
        rules("WBTCUSDT", "WBTC"), rules("OLDUSDT", "OLD", status="Closed"), rules("XRPUSDT", "XRP"),
    ]})
    turnover = {"BTCUSDT": 5, "ETHUSDT": 9, "SOLUSDT": 7, "USDCUSDT": 99, "BTC3LUSDT": 98, "SCAMUSDT": 97,
                "WBTCUSDT": 96, "OLDUSDT": 95, "XRPUSDT": 6, "NAOLISTADOUSDT": 94}
    tickers = {s: {"symbol": s, "turnover24h": str(v)} for s, v in turnover.items()}

    chosen = select_top_symbols(tickers, registry, universe, top_n=3, btc_symbol="BTCUSDT")
    assert [s for s, _ in chosen] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]  # BTC sempre primeiro


def test_btc_entra_mesmo_sem_volume_alto():
    universe = load_config(CONFIG_PATH).universe
    registry = InstrumentRegistry({r.symbol: r for r in [rules("BTCUSDT", "BTC"), rules("ETHUSDT", "ETH")]})
    tickers = {"BTCUSDT": {"turnover24h": "1"}, "ETHUSDT": {"turnover24h": "100"}}
    chosen = select_top_symbols(tickers, registry, universe, top_n=1, btc_symbol="BTCUSDT")
    assert [s for s, _ in chosen] == ["BTCUSDT"]
