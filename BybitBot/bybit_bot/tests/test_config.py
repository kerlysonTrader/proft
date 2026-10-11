from __future__ import annotations

import copy

import pytest
import yaml

from bot.config import (
    BotConfig,
    ConfigError,
    LiveModeNotConfirmedError,
    ensure_live_allowed,
    load_config,
)
from conftest import CONFIG_PATH, EXAMPLE_CONFIG_PATH


@pytest.fixture
def raw() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def validate(data: dict) -> BotConfig:
    return BotConfig.model_validate(data)


def test_config_do_projeto_e_valido():
    config = load_config(CONFIG_PATH)
    assert config.mode == "paper"
    assert config.bybit.category == "spot"
    assert config.score.weights.trend == 25


def test_config_exemplo_e_identico_ao_do_projeto():
    example = yaml.safe_load(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"))
    project = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert example == project


def test_rest_url_por_modo():
    config = load_config(CONFIG_PATH)
    assert config.rest_url_for("demo") == "https://api-demo.bybit.com"
    assert config.rest_url_for("live") == "https://api.bybit.com"
    assert config.rest_url_for("paper") == "https://api.bybit.com"


def test_campo_desconhecido_e_rejeitado(raw):
    raw["risk"]["risk_per_trade_pcct"] = 1.0
    with pytest.raises(Exception, match="risk_per_trade_pcct"):
        validate(raw)


def test_categoria_diferente_de_spot_e_rejeitada(raw):
    raw["bybit"]["category"] = "linear"
    with pytest.raises(Exception, match="category"):
        validate(raw)


@pytest.mark.parametrize(
    "path, value, fragment",
    [
        (("score", "weights", "trend"), 30, "soma dos pesos"),
        (("score", "rsi_band_4h"), [68, 50], "faixa inválida"),
        (("score", "watchlist_b_min"), 75, "watchlist_a_min"),
        (("regime", "h4_fast_ema"), 300, "h4_fast_ema"),
        (("setups", "ote_fibo", "ote_start"), 0.9, "ote_start"),
        (("exits", "tp2_r"), 1.0, "tp2_r"),
        (("risk", "max_total_exposure_pct"), 150, "max_total_exposure_pct"),
        (("risk", "max_open_positions_neutral"), 9, "max_open_positions_neutral"),
        (("onchain", "score", "max_adj"), 2, "max_adj"),
        (("onchain", "score", "can_promote"), True, "can_promote"),
        (("onchain", "risk", "on_unavailable_factor"), 0.5, "on_unavailable_factor"),
        (("mode",), "real", "mode"),
        (("timezone",), "Marte/Olympus", "fuso horário"),
        (("bybit", "rest_url", "demo"), "http://api-demo.bybit.com", "https"),
    ],
)
def test_valores_incoerentes_sao_rejeitados(raw, path, value, fragment):
    data = copy.deepcopy(raw)
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(Exception, match=fragment):
        validate(data)


def test_arquivo_inexistente(tmp_path):
    with pytest.raises(ConfigError, match="não encontrado"):
        load_config(tmp_path / "nao_existe.yaml")


def test_erro_de_validacao_vira_config_error(tmp_path, raw):
    raw["bybit"]["max_retries"] = -1
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ConfigError, match="max_retries"):
        load_config(path)


def test_modo_live_exige_confirmacao(raw):
    raw["mode"] = "live"
    config = validate(raw)
    with pytest.raises(LiveModeNotConfirmedError, match="CONFIRM_LIVE"):
        ensure_live_allowed(config, env={})
    ensure_live_allowed(config, env={"CONFIRM_LIVE": "SIM"})


def test_live_bloqueado_se_config_nao_esta_em_live(raw):
    config = validate(raw)
    with pytest.raises(LiveModeNotConfirmedError):
        ensure_live_allowed(config, env={"CONFIRM_LIVE": "SIM"})
