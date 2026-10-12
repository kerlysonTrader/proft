from __future__ import annotations

import json
from collections import Counter

import httpx
import numpy as np
import pandas as pd
import pytest

from bot.bybit.instruments import InstrumentRegistry, InstrumentRules
from bot.config import load_config
from bot.reporting.dashboard_client import DashboardClient, clean_json
from bot.scanner.features import compute_features, period_return
from bot.scanner.regime import RegimeState, breadth_pct, evaluate_regime
from bot.scanner.scanner import CoinResult, ScanResult, scanner_payload
from bot.scanner.scoring import score_features
from bot.scanner.universe import UniverseCoin, build_universe, spread_pct
from conftest import CONFIG_PATH

HOUR_MS = 3_600_000


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_PATH)


def frame(closes, freq="4h", start="2026-01-01", wick=0.002, volume=1000.0) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[:1], closes[:-1]]
    df = pd.DataFrame({
        "open": opens,
        "high": np.maximum(opens, closes) * (1 + wick),
        "low": np.minimum(opens, closes) * (1 - wick),
        "close": closes,
        "volume": volume,
        "turnover": closes * volume,
    }, index=pd.date_range(start, periods=len(closes), freq=freq, tz="UTC"))
    df.insert(0, "start_ms", df.index.astype("int64") // 1_000_000)
    return df


def uptrend(n, start=100.0, step=0.004, freq="4h"):
    return frame(start * (1 + step) ** np.arange(n), freq=freq)


def downtrend(n, start=100.0, step=0.004, freq="4h"):
    return frame(start * (1 - step) ** np.arange(n), freq=freq)


# ------------------------------------------------------------------ universo
def rules(symbol, base, status="Trading"):
    return InstrumentRules.from_api({
        "symbol": symbol, "baseCoin": base, "quoteCoin": "USDT", "status": status,
        "lotSizeFilter": {"basePrecision": "0.01", "minOrderQty": "0.01", "minOrderAmt": "1"},
        "priceFilter": {"tickSize": "0.01"}})


def ticker(price=10.0, turnover=10e6, change=0.02, bid=9.995, ask=10.005):  # spread 0,1 %
    return {"lastPrice": str(price), "turnover24h": str(turnover), "price24hPcnt": str(change),
            "bid1Price": str(bid), "ask1Price": str(ask)}


def test_spread_pct():
    assert spread_pct(99, 101) == pytest.approx(2.0)
    assert spread_pct(None, 101) is None


def test_filtros_do_universo(cfg):
    names = ["BTC", "OK", "LOWVOL", "WIDE", "PUMP", "DUMP", "USDC", "SOL3L", "OFF"]
    registry = InstrumentRegistry({f"{n}USDT": rules(f"{n}USDT", n, "Closed" if n == "OFF" else "Trading")
                                   for n in names})
    tickers = {
        "BTCUSDT": ticker(turnover=1),                        # BTC entra sempre
        "OKUSDT": ticker(),
        "LOWVOLUSDT": ticker(turnover=1e6),
        "WIDEUSDT": ticker(bid=9.9, ask=10.1),                # spread 2 %
        "PUMPUSDT": ticker(change=0.30),
        "DUMPUSDT": ticker(change=-0.20),
        "USDCUSDT": ticker(),
        "SOL3LUSDT": ticker(),
        "OFFUSDT": ticker(),
        "ETHBTC": ticker(),
    }
    result = build_universe(tickers, registry, cfg.universe, always=("BTCUSDT",))
    assert sorted(c.symbol for c in result.coins) == ["BTCUSDT", "OKUSDT"]
    assert result.rejected == Counter({
        "liquidez 24h baixa": 1, "spread alto": 1, "já esticada (alta 24h)": 1, "queda forte 24h": 1,
        "excluída (stable/atrelada/lista negra)": 1, "token alavancado": 1, "par fora de negociação": 1,
        "fora da lista de pares USDT": 1})
    ok = next(c for c in result.coins if c.symbol == "OKUSDT")
    assert ok.change_24h_pct == pytest.approx(2.0)  # fração da Bybit convertida em %


# ------------------------------------------------------------------ features
def test_period_return():
    assert period_return(pd.Series([100.0, 110, 121]), 2) == pytest.approx(0.21)
    assert np.isnan(period_return(pd.Series([1.0]), 3))


def test_features_de_tendencia_de_alta(cfg):
    h4 = uptrend(500)
    d1 = uptrend(200, step=0.01, freq="D")
    h1 = uptrend(200, step=0.001, freq="h")
    btc = uptrend(200, step=0.002, freq="D")
    f = compute_features("UPUSDT", d1, h4, h1, btc, None, cfg.indicators, cfg.score)
    assert f.close_4h > f.ema50_4h > f.ema200_4h
    assert f.plus_di_4h > f.minus_di_4h
    assert f.ret_short > f.btc_ret_short
    assert f.ratio_btc > f.ratio_btc_ema
    assert f.range_position_4h > 0.9  # perto da máxima (o pavio sintético fica um pouco acima)
    assert f.daily_candles == 200
    r = score_features(f, cfg.score)
    assert r.components["trend"] == 25
    assert r.components["relative_strength"] == 20


def test_features_de_tendencia_de_baixa(cfg):
    f = compute_features("DOWNUSDT", downtrend(200, freq="D"), downtrend(500), downtrend(200, freq="h"),
                         uptrend(200, freq="D"), None, cfg.indicators, cfg.score)
    r = score_features(f, cfg.score)
    assert r.components["trend"] == 0
    assert r.components["relative_strength"] == 0


def test_volume_ratio_usa_24h_de_velas_1h(cfg):
    d1 = uptrend(60, freq="D")
    d1["turnover"] = 1000.0
    h1 = uptrend(48, freq="h")
    h1["turnover"] = 2000 / 24  # soma 24h = 2000 = 2x a média diária
    f = compute_features("VUSDT", d1, uptrend(300), h1, uptrend(60, freq="D"), None, cfg.indicators, cfg.score)
    assert f.volume_ratio == pytest.approx(2.0)


def test_pavio_superior(cfg):
    d1 = uptrend(60, freq="D")
    d1.iloc[-2, d1.columns.get_loc("high")] = d1["close"].iloc[-2] * 1.2  # pavio enorme
    f = compute_features("WUSDT", d1, uptrend(300), uptrend(48, freq="h"), uptrend(60, freq="D"), None,
                         cfg.indicators, cfg.score)
    assert f.max_upper_wick_fraction_1d > 0.6


def test_features_sem_dados_ficam_nan(cfg):
    empty = frame([], freq="h")
    f = compute_features("XUSDT", empty, empty, empty, empty, None, cfg.indicators, cfg.score)
    assert np.isnan(f.close_4h) and f.daily_candles == 0


# ------------------------------------------------------------------ regime
@pytest.mark.parametrize(
    "d1, h4, expected",
    [
        (uptrend(300, freq="D"), uptrend(500), "risk_on"),
        (uptrend(300, freq="D"), downtrend(500), "neutro"),
        (downtrend(300, freq="D"), uptrend(500), "neutro"),
        (downtrend(300, freq="D"), downtrend(500), "risk_off"),
    ],
)
def test_regime(cfg, d1, h4, expected):
    rg = evaluate_regime(d1, h4, uptrend(48, freq="h"), 60.0, RegimeState(), 0, cfg.regime)
    assert rg.regime == expected
    assert rg.allow_new_entries == (expected != "risk_off")


def test_amplitude_baixa_vira_risk_off(cfg):
    rg = evaluate_regime(uptrend(300, freq="D"), uptrend(500), uptrend(48, freq="h"), 20.0, RegimeState(), 0,
                         cfg.regime)
    assert rg.regime == "risk_off"
    assert breadth_pct([True, False, False, False]) == 25
    assert breadth_pct([]) is None


def test_btc_sem_historico_e_risk_off(cfg):
    rg = evaluate_regime(uptrend(50, freq="D"), uptrend(100), uptrend(48, freq="h"), 60.0, RegimeState(), 0,
                         cfg.regime)
    assert rg.regime == "risk_off"


def test_circuit_breaker_dispara_e_dura_12h(cfg):
    h1 = frame(np.r_[np.full(30, 100.0), np.full(10, 93.0)], freq="h")  # −7 % em 24 h
    state = RegimeState()
    now = 1_000 * HOUR_MS
    rg = evaluate_regime(uptrend(300, freq="D"), uptrend(500), h1, 60.0, state, now, cfg.regime)
    assert rg.circuit_breaker_active and not rg.allow_new_entries
    assert state.circuit_until_ms == now + 12 * HOUR_MS

    calm = uptrend(48, freq="h")
    later = evaluate_regime(uptrend(300, freq="D"), uptrend(500), calm, 60.0, state, now + 11 * HOUR_MS, cfg.regime)
    assert later.circuit_breaker_active
    done = evaluate_regime(uptrend(300, freq="D"), uptrend(500), calm, 60.0, state, now + 13 * HOUR_MS, cfg.regime)
    assert not done.circuit_breaker_active and done.allow_new_entries


def test_estado_do_regime_persiste(tmp_path):
    path = tmp_path / "state.json"
    RegimeState(circuit_until_ms=123).save(path)
    assert RegimeState.load(path).circuit_until_ms == 123
    assert RegimeState.load(tmp_path / "nao_existe.json").circuit_until_ms is None


# ------------------------------------------------------------------ payload e painel
def test_payload_do_scanner_run(cfg):
    rg = evaluate_regime(uptrend(300, freq="D"), uptrend(500), uptrend(48, freq="h"), 60.0, RegimeState(), 0,
                         cfg.regime)
    f = compute_features("UPUSDT", uptrend(200, freq="D"), uptrend(500), uptrend(48, freq="h"),
                         uptrend(200, freq="D"), None, cfg.indicators, cfg.score)
    coin = UniverseCoin("UPUSDT", "UP", 10.0, 2.0, 1e7, 0.05)
    result = CoinResult(coin, f, score_features(f, cfg.score), "A")
    scan = ScanResult(1_791_763_200_000, 30_000, rg, [result], Counter({"liquidez 24h baixa": 3}))
    payload = scanner_payload(scan, cfg.score, 150)
    run, row = payload["run"], payload["results"][0]
    assert run["regime"] == "risk_on" and run["candidates"] == 1 and run["universe_size"] == 1
    assert run["run_at"].endswith("Z") and "liquidez 24h baixa: 3" in run["notes"]
    assert row["status"] == "watch"
    assert row["reasons"][0] == "Watchlist A (score ≥ 70)"
    assert set(row) >= {"score_trend", "score_relative_strength", "score_volume", "score_squeeze",
                        "score_derivatives", "score_momentum", "penalties", "rsi_1h", "rsi_4h", "atr_pct"}
    json.dumps(clean_json(payload), allow_nan=False)  # JSON válido, sem NaN


def test_clean_json_troca_nan():
    assert clean_json({"a": float("nan"), "b": [1.0, float("inf")]}) == {"a": None, "b": [1.0, None]}


def dashboard(handler, sleeps):
    return DashboardClient("https://painel/api", "bot_token123", max_retries=2,
                           http_client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=sleeps.append)


def test_painel_ok_envia_token_e_user_agent():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "id": "abc"})

    result = dashboard(handler, []).send("scanner_run", {"run": {}, "results": [], "x": float("nan")})
    assert result.ok and result.body["id"] == "abc"
    assert seen[0].headers["x-bot-token"] == "bot_token123"
    assert seen[0].headers["User-Agent"].startswith("bybit-scanner-bot")
    assert json.loads(seen[0].content)["payload"]["x"] is None


@pytest.mark.parametrize("status", [400, 401, 403])
def test_painel_erro_de_contrato_nao_repete(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"ok": False})

    result = dashboard(handler, []).send("scanner_run", {})
    assert not result.ok and not result.requeue and len(calls) == 1


def test_painel_fora_do_ar_repete_e_pede_reenfileirar():
    sleeps = []
    result = dashboard(lambda r: httpx.Response(503, json={"ok": False}), sleeps).send("heartbeat", {})
    assert not result.ok and result.requeue
    assert sleeps == [1, 2]


def test_painel_falha_de_rede_nao_levanta_excecao():
    def handler(request):
        raise httpx.ConnectError("sem rede")

    result = dashboard(handler, []).send("heartbeat", {})
    assert not result.ok and result.requeue


@pytest.mark.parametrize("reason, requeue", [("not_found", True), ("closed", False)])
def test_painel_409(reason, requeue):
    result = dashboard(lambda r: httpx.Response(409, json={"ok": False, "reason": reason}), []).send("x", {})
    assert result.requeue is requeue
