from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bot.bybit.instruments import InstrumentRules
from bot.config import load_config
from bot.exits.position import Position, on_candle_close, process_candle
from bot.risk.risk_manager import OpenExposure, RiskManager
from conftest import CONFIG_PATH

H = 3_600_000


def ms(y, m, d, h=0) -> int:
    return int(datetime(y, m, d, h, tzinfo=UTC).timestamp() * 1000)


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_PATH)


def size(rm, **kw):
    base = dict(symbol="XUSDT", base="X", entry=100.0, stop=95.0, equity=1000.0, free_cash=1000.0, exposures=[],
                regime="risk_on", now_ms=ms(2026, 10, 12, 12))
    base.update(kw)
    return rm.size(**base)


# ------------------------------------------------------------------ tamanho da posição
def test_tamanho_por_risco(cfg):
    d = size(RiskManager(cfg.risk, 1000))
    assert d.ok
    assert d.risk_pct == 1.0
    assert d.qty == pytest.approx(2.0)          # 10 USDT de risco / 5 por unidade
    assert d.risk_usdt == pytest.approx(10.0)


def test_regime_neutro_e_cautela_reduzem_risco(cfg):
    rm = RiskManager(cfg.risk, 1000)
    assert size(rm, regime="neutro").qty == pytest.approx(1.0)
    assert size(rm, regime="neutro", caution=True).qty == pytest.approx(0.5)


def test_tetos_de_exposicao_e_caixa(cfg):
    rm = RiskManager(cfg.risk, 1000)
    d = size(rm, stop=99.0)  # risco 1 por unidade -> 10 unidades = 1000 USDT > 25 % por moeda
    assert d.notional == pytest.approx(250.0)
    assert any("exposição por moeda" in r for r in d.reasons)
    d = size(rm, stop=99.0, exposures=[OpenExposure("A", 700)])  # total 80 % -> sobram 100
    assert d.notional == pytest.approx(100.0)
    d = size(rm, stop=99.0, free_cash=60.0)
    assert d.notional == pytest.approx(60.0)


def test_minimo_e_regras_do_par(cfg):
    rm = RiskManager(cfg.risk, 1000)
    assert not size(rm, free_cash=3.0).ok  # 3 USDT < mínimo
    rules = InstrumentRules.from_api({"symbol": "XUSDT", "baseCoin": "X", "quoteCoin": "USDT", "status": "Trading",
                                      "lotSizeFilter": {"basePrecision": "0.1", "minOrderQty": "0.1",
                                                        "minOrderAmt": "5"},
                                      "priceFilter": {"tickSize": "0.01"}})
    d = size(rm, stop=93.0, rules=rules)  # 10/7 = 1,428 -> arredonda para baixo: 1,4
    assert d.qty == pytest.approx(1.4)


@pytest.mark.parametrize(
    "kw, fragment",
    [
        ({"regime": "risk_off"}, "risk_off"),
        ({"exposures": [OpenExposure(f"S{i}", 10) for i in range(4)]}, "limite de 4"),
        ({"regime": "neutro", "exposures": [OpenExposure("A", 10), OpenExposure("B", 10)]}, "limite de 2"),
        ({"exposures": [OpenExposure("XUSDT", 10)]}, "já há posição"),
        ({"stop": 101.0}, "stop acima"),
    ],
)
def test_bloqueios_de_entrada(cfg, kw, fragment):
    d = size(RiskManager(cfg.risk, 1000), **kw)
    assert not d.ok and any(fragment in r for r in d.reasons), d.reasons


def test_limite_por_setor(cfg):
    risk = cfg.risk.model_copy(update={"sectors": {"X": "L1", "A": "L1", "B": "L1"}})
    d = size(RiskManager(risk, 1000), exposures=[OpenExposure("AUSDT", 10, "L1"), OpenExposure("BUSDT", 10, "L1")])
    assert not d.ok and any("setor L1" in r for r in d.reasons)


def test_perda_diaria_bloqueia_ate_meia_noite(cfg):
    rm = RiskManager(cfg.risk, 1000)
    rm.mark(1000, ms(2026, 10, 12, 1))
    rm.mark(965, ms(2026, 10, 12, 10))
    assert any("perda do dia" in r for r in rm.block_reasons(965, ms(2026, 10, 12, 10)))
    rm.mark(965, ms(2026, 10, 13, 0))  # novo dia
    assert rm.block_reasons(965, ms(2026, 10, 13, 0)) == []


def test_perdas_seguidas_pausam(cfg):
    rm = RiskManager(cfg.risk, 1000)
    now = ms(2026, 10, 12, 12)
    for _ in range(3):
        rm.on_trade_closed(-5, now)
    assert any("perdas seguidas" in r for r in rm.block_reasons(1000, now + H))
    assert rm.block_reasons(1000, now + 25 * H) == []
    rm.on_trade_closed(-5, now)
    rm.on_trade_closed(+5, now)  # ganho zera a sequência
    assert rm.state.consecutive_losses == 0


def test_drawdown_semanal_pausa_ate_segunda(cfg):
    rm = RiskManager(cfg.risk, 1000)
    rm.mark(1000, ms(2026, 10, 12, 1))   # segunda-feira
    rm.mark(935, ms(2026, 10, 14, 1))    # −6,5 % na semana
    assert any("semanal" in r for r in rm.block_reasons(935, ms(2026, 10, 16, 1)))
    assert not any("semanal" in r for r in rm.block_reasons(935, ms(2026, 10, 19, 1)))


def test_kill_switch_no_drawdown_desde_o_pico(cfg):
    rm = RiskManager(cfg.risk, 1000)
    rm.mark(1200, ms(2026, 10, 1))
    rm.mark(1015, ms(2026, 10, 20))     # −15,4 % do pico
    assert rm.state.kill_switch
    assert any("kill switch" in r for r in rm.block_reasons(1100, ms(2026, 11, 20)))  # não destrava sozinho


# ------------------------------------------------------------------ saídas
def pos(**kw) -> Position:
    base = dict(symbol="XUSDT", setup="pullback_tendencia", entry=100.0, qty=10.0, stop=95.0, tp1=107.5,
                tp2=115.0, opened_ms=0, fee_rate=0.001)
    base.update(kw)
    return Position(**base)


def test_stop_com_slippage_e_gap(cfg):
    p = pos()
    fills = process_candle(p, 99, 100, 94, H, cfg.exits, 0.05)
    assert fills[0].reason == "stop" and fills[0].price == pytest.approx(95 * 0.9995)
    p = pos()
    fills = process_candle(p, 90, 92, 89, H, cfg.exits, 0.0)   # abriu abaixo do stop
    assert fills[0].price == 90
    assert p.closed and p.r_multiple < -1  # gap + taxas pioram o −1 R


def test_stop_e_alvo_na_mesma_vela_conta_o_stop(cfg):
    p = pos()
    fills = process_candle(p, 100, 110, 94, H, cfg.exits, 0.0)
    assert [f.reason for f in fills] == ["stop"]


def test_tp1_parcial_e_breakeven(cfg):
    p = pos()
    fills = process_candle(p, 101, 108, 100.5, H, cfg.exits, 0.0)
    assert [f.reason for f in fills] == ["tp1"] and fills[0].qty == pytest.approx(5.0)
    assert p.tp1_hit and p.stop == pytest.approx(100.2) and p.stop_kind == "breakeven"
    fills = process_candle(p, 101, 101.5, 100.0, 2 * H, cfg.exits, 0.0)
    assert fills[0].reason == "breakeven" and p.closed
    assert p.pnl > 0  # metade no TP1 + metade no breakeven (que já cobre as taxas)


def test_tp1_e_volta_ao_breakeven_na_mesma_vela(cfg):
    p = pos()
    fills = process_candle(p, 101, 108, 100.1, H, cfg.exits, 0.0)
    assert [f.reason for f in fills] == ["tp1", "breakeven"] and p.closed


def test_modo_tp2_fixo(cfg):
    exits = cfg.exits.model_copy(update={"mode_after_tp1": "fixed_tp2"})
    p = pos()
    process_candle(p, 101, 108, 101, H, exits, 0.0)
    fills = process_candle(p, 108, 116, 107, 2 * H, exits, 0.0)
    assert fills[0].reason == "tp2" and fills[0].price == 115 and p.closed
    assert p.r_multiple == pytest.approx((0.5 * 7.5 + 0.5 * 15) / 5 - p.fees / 50)


def test_trailing_depois_do_tp1(cfg):
    p = pos()
    process_candle(p, 101, 108, 101, H, cfg.exits, 0.0)
    on_candle_close(p, close=109, recent_lows=[104, 105, 106], atr_1h=2.0, ts_ms=2 * H, exits=cfg.exits,
                    slippage_pct=0.0)
    assert p.stop == pytest.approx(103.0) and p.stop_kind == "trailing"   # mín(104,105,106) − 0,5 × 2
    on_candle_close(p, close=109, recent_lows=[100, 101, 102], atr_1h=2.0, ts_ms=3 * H, exits=cfg.exits,
                    slippage_pct=0.0)
    assert p.stop == pytest.approx(103.0)  # trailing nunca desce


def test_stop_de_tempo(cfg):
    p = pos()
    process_candle(p, 100, 102, 99, H, cfg.exits, 0.0)   # máximo +0,4 R
    assert on_candle_close(p, close=101, recent_lows=[99], atr_1h=1, ts_ms=47 * H, exits=cfg.exits,
                           slippage_pct=0.0) is None
    fill = on_candle_close(p, close=101, recent_lows=[99], atr_1h=1, ts_ms=48 * H, exits=cfg.exits, slippage_pct=0.0)
    assert fill.reason == "tempo" and p.closed


def test_stop_de_tempo_nao_age_se_chegou_a_meio_r(cfg):
    p = pos()
    process_candle(p, 100, 103, 99, H, cfg.exits, 0.0)   # +0,6 R
    assert on_candle_close(p, close=101, recent_lows=[99], atr_1h=1, ts_ms=60 * H, exits=cfg.exits,
                           slippage_pct=0.0) is None


def test_invalidacao_4h(cfg):
    p = pos()
    fill = on_candle_close(p, close=98, recent_lows=[97], atr_1h=1, ts_ms=4 * H, exits=cfg.exits, slippage_pct=0.0,
                           close_4h_below_ema50=True)
    assert fill.reason == "invalidacao"


def test_risk_off_leva_lucro_ao_breakeven(cfg):
    p = pos()
    on_candle_close(p, close=104, recent_lows=[103], atr_1h=1, ts_ms=2 * H, exits=cfg.exits, slippage_pct=0.0,
                    regime_risk_off=True)
    assert p.stop == pytest.approx(p.breakeven) and p.stop_kind == "breakeven"
    q = pos()
    on_candle_close(q, close=99, recent_lows=[98], atr_1h=1, ts_ms=2 * H, exits=cfg.exits, slippage_pct=0.0,
                    regime_risk_off=True)
    assert q.stop == 95  # sem lucro: não mexe


def test_resultado_com_taxas():
    p = pos()
    p._exit(10, 110, "tp2", H)
    assert p.fees == pytest.approx(0.001 * (1000 + 1100))
    assert p.pnl == pytest.approx(100 - 2.1)
    assert p.r_multiple == pytest.approx((100 - 2.1) / 50)
