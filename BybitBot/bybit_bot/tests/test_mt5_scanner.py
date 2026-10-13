from __future__ import annotations

import math
import subprocess

import pandas as pd
import pytest

from bot.bybit.client import KLINE_INTERVAL_MS, Kline
from bot.config import load_config
from bot.markets.mt5_scanner import Mt5Scanner, group_config, mt5_payload, real_price_reason
from bot.markets.mt5_source import SymbolMeta
from bot.markets.stats import MIN_TRADES, load_stats, stats_lines
from bot.secrets import SecretProvider
from conftest import CONFIG_PATH

NOW_MS = 1_791_000_000_000
DAY_MS = 86_400_000


class FakeReader:
    """Mesma interface de leitura do Mt5Reader: tendência de alta em ALTA.s e de baixa em BAIXA.s."""

    SLOPES = {"ALTA.s": 0.004, "BAIXA.s": -0.004}   # por dia

    def __init__(self, stale_ms: int = 0):
        self.stale_ms = stale_ms

    def _price(self, symbol: str, ms: float) -> float:
        days = (ms - NOW_MS) / DAY_MS
        return 100 * math.exp(self.SLOPES[symbol] * days) * (1 + 0.004 * math.sin(days * 9))

    def rates(self, symbol: str, interval: str, count: int | None = None) -> list[Kline]:
        step = KLINE_INTERVAL_MS[interval]
        last_open = (NOW_MS - self.stale_ms) // step * step - step   # última vela FECHADA
        out = []
        for k in range(count or 500, 0, -1):
            start = last_open - (k - 1) * step
            o, c = self._price(symbol, start), self._price(symbol, start + step)
            volume = step / 60_000   # proporcional à duração: 24 velas 1H = 1 vela diária
            # pavios assimétricos: a vela seguinte a um topo não empata a máxima (senão não há pivô)
            high = c * 1.0007 if c > o else o * 1.0003
            low = c * 0.9993 if c < o else o * 0.9997
            out.append(Kline(start, interval, o, high, low, c, volume, volume * c, symbol))
        return out

    def meta(self, symbol: str) -> SymbolMeta:
        return SymbolMeta(symbol, 2, 0.01, 2, 99.99, 100.01)


@pytest.fixture(scope="module")
def config():
    cfg = load_config(CONFIG_PATH)
    mt5 = cfg.markets.mt5.model_copy(update={"groups": {"teste": ["ALTA.s", "BAIXA.s"]}, "benchmarks": {},
                                             "stop_pct_range": {"teste": (0.1, 2.0)}})
    return cfg.model_copy(update={"markets": cfg.markets.model_copy(update={"mt5": mt5})})


@pytest.fixture(scope="module")
def scan(config):
    return Mt5Scanner(FakeReader(), config, now_ms=lambda: NOW_MS).run()


def test_compra_e_venda_de_cada_ativo(scan):
    assert sorted(r.label for r in scan.rows) == ["ALTA · compra", "ALTA · venda", "BAIXA · compra", "BAIXA · venda"]
    score = {r.label: r.score.total for r in scan.rows}
    assert score["ALTA · compra"] > score["ALTA · venda"]
    assert score["BAIXA · venda"] > score["BAIXA · compra"]
    assert all(r.market_open for r in scan.rows)
    assert "teste · compra" in scan.regimes and scan.regimes["teste · venda"].regime == "risk_on"


def test_preco_e_variacao_sao_do_grafico_real(scan):
    up = next(r for r in scan.rows if r.label == "ALTA · venda")
    down = next(r for r in scan.rows if r.label == "BAIXA · venda")
    assert up.price > 99 and up.change_24h_pct > 0      # venda de ALTA ainda mostra o preço e a alta reais
    assert down.change_24h_pct < 0


def test_planos_de_venda_no_preco_real(scan, config):
    sell = next(r for r in scan.rows if r.label == "BAIXA · venda")
    assert sell.watchlist in ("A", "B")
    plans = [p for p in sell.plans if p.startswith("Plano")]
    assert plans and all(" VENDA" in p for p in plans)
    assert any("Histórico" in p for p in sell.plans)


def test_payload_do_painel(scan, config):
    payload = mt5_payload(scan, config.score, 150)
    assert payload["run"]["regime"] == "MT5"
    assert payload["run"]["universe_size"] == 4
    row = next(r for r in payload["results"] if r["symbol"] == "BAIXA · venda")
    assert row["status"] in ("watch", "watch_b")
    assert row["turnover_24h_usdt"] == 0
    assert row["rsi_4h"] < 50   # RSI mostrado no preço real (em queda)
    assert any("abaixo da EMA50" in x for x in row["reasons"])


def test_mercado_fechado_nao_gera_alerta(config):
    scan = Mt5Scanner(FakeReader(stale_ms=3 * 3_600_000), config, now_ms=lambda: NOW_MS).run()
    assert not any(r.market_open for r in scan.rows)
    assert scan.alerts == []


def test_config_do_grupo_e_intraday_com_stop_do_grupo(config):
    g = group_config(config, "teste")
    assert (g.setups.trigger_interval, g.setups.context_interval) == ("15", "60")
    assert (g.setups.common.min_stop_pct, g.setups.common.max_stop_pct) == (0.1, 2.0)


@pytest.mark.parametrize("text, expected", [
    ("Preço acima da EMA50 4H (+7)", "Preço abaixo da EMA50 4H (+7)"),
    ("ADX 4H 29 > 20 com DI+ > DI− (+6)", "ADX 4H 29 > 20 com DI− > DI+ (+6)"),
    ("OBV 4H acima da sua média e subindo (+6)", "OBV 4H abaixo da sua média e caindo (+6)"),
    ("RSI 4H 60 entre 50 e 70 (+5)", "RSI 4H 40 entre 30 e 50 (+5)"),
    ("RSI 4H 78 sobrecomprado (> 75) (−10)", "RSI 4H 22 sobrevendido (< 25) (−10)"),
    ("CMF 4H 0.12 > 0.05 (+6)", "CMF 4H -0.12 < -0.05 (+6)"),
    ("ATR 4H abaixo da própria média (contração) (+3)", "ATR 4H abaixo da própria média (contração) (+3)"),
    ("Retorno 7d acima do BTC (+2,0%) (+6)", "Retorno 7d abaixo da referência (−2,0%) (+6)"),
])
def test_motivos_da_venda_no_preco_real(text, expected):
    assert real_price_reason(text, -1) == expected


def test_motivos_da_compra_so_trocam_o_btc():
    assert real_price_reason("Retorno 7d acima do BTC (+2,0%) (+6)", 1) == "Retorno 7d acima da referência (+2,0%) (+6)"


# ------------------------------------------------------------------ estatística do backtest
def test_estatistica_do_backtest(tmp_path):
    csv = tmp_path / "t.csv"
    rows = [("pullback_tendencia", 1.0)] * 20 + [("pullback_tendencia", -1.0)] * 15 + [("ote_fibo", 2.0)] * 5
    pd.DataFrame(rows, columns=["setup", "r"]).to_csv(csv, index=False)
    stats = load_stats(csv)
    assert stats["pullback_tendencia"].trades == 35
    assert stats["todos"].trades == 40 >= MIN_TRADES and stats["todos"].has_edge
    line = stats_lines(stats, "metais · compra")[0]
    assert "pullback 35 trades, acerto 57%" in line and "✅" in line
    assert "ainda não rodado" in stats_lines(load_stats(tmp_path / "nao_existe.csv"), "x")[0]


def test_estatistica_sem_vantagem(tmp_path):
    csv = tmp_path / "t.csv"
    pd.DataFrame([("pullback_tendencia", -0.3)] * 40, columns=["setup", "r"]).to_csv(csv, index=False)
    assert "não recomendado" in stats_lines(load_stats(csv), "forex · compra")[0]


# ------------------------------------------------------------------ token do painel pelo gcloud (PC)
def test_segredo_pelo_gcloud_quando_nao_ha_biblioteca(monkeypatch):
    calls = []

    def runner(args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="token-do-painel\n", stderr="")

    provider = SecretProvider(project="meu-projeto", env={}, gcloud_runner=runner)
    monkeypatch.setattr(provider, "_client", lambda: (_ for _ in ()).throw(ImportError("sem biblioteca")))
    assert provider.get("BOT_INGEST_TOKEN") == "token-do-painel"
    assert calls == [["secrets", "versions", "access", "latest", "--secret=BOT_INGEST_TOKEN",
                      "--project=meu-projeto"]]


def test_gcloud_com_erro_vira_segredo_ausente(monkeypatch):
    provider = SecretProvider(project="p", env={},
                              gcloud_runner=lambda a: subprocess.CompletedProcess(a, 1, stdout="", stderr="x"))
    monkeypatch.setattr(provider, "_client", lambda: (_ for _ in ()).throw(ImportError("sem biblioteca")))
    assert provider.get("BOT_INGEST_TOKEN", required=False) is None


# ------------------------------------------------------------------ analista Gemini no scanner
def test_gemini_analisa_a_watchlist_e_vai_ao_painel(config):
    from bot.ai.gemini_analyst import Analysis, GeminiVerdict

    class FakeAnalyst:
        def __init__(self):
            self.keys = []

        def analyze(self, key, kind, context):
            self.keys.append((key, kind, context["direcao"]))
            return Analysis(GeminiVerdict(veredito="cautela", risco="medio", resumo="CPI amanhã"), ok=True)

    analyst = FakeAnalyst()
    cfg = config.model_copy(update={"gemini": config.gemini.model_copy(update={"analyze_watchlists": ["A", "B"]})})
    scan = Mt5Scanner(FakeReader(), cfg, now_ms=lambda: NOW_MS, analyst=analyst).run()
    analyzed = [r for r in scan.rows if r.gemini]
    assert analyzed and all(r.watchlist in ("A", "B") for r in analyzed)
    assert all(kind == "mt5" and key.startswith("mt5:") for key, kind, _ in analyst.keys)
    row = next(x for x in mt5_payload(scan, cfg.score, 150)["results"] if x["gemini_verdict"])
    assert row["gemini_verdict"] == "cautela" and row["gemini_summary"] == "CPI amanhã"
    assert any(x.startswith("Gemini: cautela") for x in row["reasons"])


def test_planos_estruturados_para_o_grafico(scan, config):
    row = next(r for r in mt5_payload(scan, config.score, 150)["results"] if r["symbol"] == "BAIXA · venda")
    assert row["plans"], "linha da Watchlist deve levar os planos em números"
    for p in row["plans"]:
        assert p["lado"] == "venda" and p["stop"] > p["entrada"] > p["tp1"] > p["tp2"]
        assert p["setup"] in ("Pullback", "Rompimento") and p["alerta"] is False
    zone = next(p["zona"] for p in row["plans"] if p["setup"] == "Pullback")
    assert zone[0] < zone[1]


def test_leitura_de_estrutura_no_painel(scan, config):
    row = next(r for r in mt5_payload(scan, config.score, 150)["results"] if r["symbol"] == "ALTA · compra")
    lines = [x for x in row["reasons"] if x.startswith("📐")]
    assert any(x.startswith("📐 Estrutura 1H:") for x in lines)
    assert any(x.startswith("📐 Estrutura 15m:") for x in lines)
    assert any(x.startswith("📐 Médias 15m:") for x in lines)


def test_estrutura_em_numeros_para_o_radar(scan, config):
    row = next(r for r in mt5_payload(scan, config.score, 150)["results"] if r["symbol"] == "ALTA · compra")
    data = row["structure"]
    assert set(data["tempos"]) == {"15m", "1H", "4H"}
    m15 = data["tempos"]["15m"]
    assert m15["tendencia"] in ("alta", "baixa", "lateral")
    assert set(m15["medias"]) == {"9", "21", "50", "200"}
    assert m15["alinhamento"] in ("alta", "baixa", "nenhum") and isinstance(m15["eventos"], list)
    assert data["gatilho"] and "backtest" in data["nota"]


def test_contexto_de_mercado_e_fatores(scan, config):
    row = next(r for r in mt5_payload(scan, config.score, 150)["results"] if r["symbol"] == "ALTA · compra")
    ctx, fat = row["structure"]["contexto"], row["structure"]["fatores"]
    assert ctx["zona"] in ("desconto", "equilibrio", "premium") and 0 <= ctx["posicao"] <= 1
    assert ctx["faixa_min"] <= ctx["preco"] <= ctx["faixa_max"] and ctx["vwap"] is not None
    assert ctx["tendencia_dominante"] in ("alta", "baixa", "lateral")
    assert fat["alta"] + fat["baixa"] + fat["neutro"] == len(fat["itens"]) >= 8
    assert fat["vies"] in ("alta", "baixa", "neutro") and "não é probabilidade" in fat["nota"]
    assert fat["alta"] > fat["baixa"]   # o ativo de teste está em alta
