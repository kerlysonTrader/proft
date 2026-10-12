from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from bot.backtest.engine import Backtester, load_symbol
from bot.backtest.report import Metrics, gate_checks, max_drawdown_pct, render_markdown, score_band
from bot.backtest.walk_forward import walk_forward_windows
from bot.bybit.client import Kline
from bot.config import load_config
from bot.data.market_data import klines_to_frame
from bot.scanner.features import FEATURE_COLUMNS, compute_features, feature_frame
from bot.storage.kline_store import KlineStore
from conftest import CONFIG_PATH

H = 3_600_000
T0 = 1_735_689_600_000  # 2025-01-01 00:00 UTC


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_PATH)


def synthetic(symbol: str, hours: int, seed: int, drift: float = 0.0004, vol: float = 0.008, price=100.0):
    """Velas 1H aleatórias + 4H e 1D agregadas a partir delas (coerentes entre si)."""
    rng = np.random.default_rng(seed)
    closes = price * np.exp(np.cumsum(rng.normal(drift, vol, hours)))
    opens = np.r_[price, closes[:-1]]
    highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, vol / 2, hours)))
    lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, vol / 2, hours)))
    volume = rng.uniform(5e4, 2e5, hours)
    h1 = [Kline(T0 + i * H, "60", opens[i], highs[i], lows[i], closes[i], volume[i], volume[i] * closes[i], symbol)
          for i in range(hours)]
    frame = klines_to_frame(h1)

    def agg(rule: str, interval: str, step: int):
        g = frame.resample(rule).agg({"start_ms": "first", "open": "first", "high": "max", "low": "min",
                                      "close": "last", "volume": "sum", "turnover": "sum"}).dropna()
        return [Kline(int(r.start_ms), interval, r.open, r.high, r.low, r.close, r.volume, r.turnover, symbol)
                for r in g.itertuples()]

    return h1, agg("4h", "240", 4), agg("1D", "D", 24)


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    s = KlineStore(tmp_path_factory.mktemp("bt") / "h.db")
    for sym, seed, drift in (("BTCUSDT", 1, 0.0003), ("AAAUSDT", 2, 0.0006), ("BBBUSDT", 3, 0.0004)):
        for series in synthetic(sym, 24 * 150, seed, drift):
            s.upsert(series)
    return s


def test_features_em_lote_iguais_as_do_robo(cfg, store):
    """feature_frame (backtest) == compute_features (robô ao vivo) com o mesmo histórico até T."""
    d1 = klines_to_frame(store.load("AAAUSDT", "D"))
    h4 = klines_to_frame(store.load("AAAUSDT", "240"))
    h1 = klines_to_frame(store.load("AAAUSDT", "60"))
    btc = klines_to_frame(store.load("BTCUSDT", "D"))
    frame = feature_frame(d1, h4, h1, btc, cfg.indicators, cfg.score)
    for k in (300, 1501, 2222, 3500):
        ts = int(h1["start_ms"].iloc[k]) + H

        def upto(df, step):
            return df[df["start_ms"] + step <= ts]

        live = compute_features("AAAUSDT", upto(d1, 24 * H), upto(h4, 4 * H), upto(h1, H), upto(btc, 24 * H), None,
                                cfg.indicators, cfg.score)
        row = frame.loc[ts]
        for col in FEATURE_COLUMNS:
            a, b = getattr(live, col), row[col]
            assert (math.isnan(a) and math.isnan(b)) or a == pytest.approx(b, rel=1e-9, abs=1e-9), (k, col, a, b)


def run(cfg, store, **cfg_updates):
    c = cfg.model_copy(update=cfg_updates) if cfg_updates else cfg
    btc = load_symbol(store, "BTCUSDT", "BTC", None, c)
    data = {"BTCUSDT": btc}
    for sym in ("AAAUSDT", "BBBUSDT"):
        data[sym] = load_symbol(store, sym, sym[:3], btc.d1, c)
    start = T0 + 60 * 24 * H
    return Backtester(c, data, start, T0 + 150 * 24 * H).run()


def test_backtest_contabilidade_fecha(cfg, store):
    # liquidez sintética é baixa: afrouxa o filtro de giro para o universo ter moedas
    universe = cfg.universe.model_copy(update={"min_turnover_24h_usdt": 1.0})
    score = cfg.score.model_copy(update={"watchlist_a_min": 40, "watchlist_b_min": 30})
    result = run(cfg, store, universe=universe, score=score)
    assert not result.equity.empty
    final = float(result.equity.iloc[-1])
    assert final == pytest.approx(result.initial_equity + sum(t.pnl for t in result.trades), abs=1e-6)
    for t in result.trades:
        assert t.closed_ms >= t.opened_ms
        assert t.exit_reason
    assert result.orders_placed >= len(result.trades)


def test_sem_moedas_elegiveis_nao_opera(cfg, store):
    result = run(cfg, store)  # filtro de liquidez real (5 M USDT): nada passa
    assert result.trades == []
    assert float(result.equity.iloc[-1]) == pytest.approx(result.initial_equity)


def test_relatorio_e_gate(cfg, store):
    universe = cfg.universe.model_copy(update={"min_turnover_24h_usdt": 1.0})
    score = cfg.score.model_copy(update={"watchlist_a_min": 40, "watchlist_b_min": 30})
    result = run(cfg, store, universe=universe, score=score)
    windows = walk_forward_windows(result, cfg.backtest.walk_forward)
    text = render_markdown(result, cfg, windows)
    assert "## Gate 5" in text and "Walk-forward" in text and "Limitações" in text
    checks = gate_checks(result, cfg.backtest.gate, windows)
    assert any(c.name.startswith("≥ 12 meses") and not c.passed for c in checks)  # só ~3 meses simulados


def test_metricas_e_auxiliares():
    from bot.backtest.engine import TradeRecord

    def tr(pnl, r):
        return TradeRecord("X", "pullback_tendencia", 75, "risk_on", 0, H, 1, 1, 1, pnl, r, 0.1, "stop", False)

    m = Metrics.of([tr(20, 2.0), tr(-10, -1.0), tr(-10, -1.0), tr(30, 3.0)])
    assert m.trades == 4 and m.win_rate == 50
    assert m.expectancy_r == pytest.approx(0.75)
    assert m.profit_factor == pytest.approx(50 / 20)
    assert m.payoff == pytest.approx(2.5)
    assert max_drawdown_pct(pd.Series([100, 120, 90, 130])) == pytest.approx(25.0)
    assert score_band(72) == "70–75" and score_band(95) == "90–100"
