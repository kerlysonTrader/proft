from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from bot.logging_setup import get_logger, register_secret, setup_logging
from bot.secrets import SecretNotFoundError, SecretProvider


def test_le_de_variaveis_de_ambiente_sem_gcp_project():
    provider = SecretProvider(env={"BYBIT_API_KEY": "  chave-local-123 \n"})
    assert provider.source == "variáveis de ambiente"
    assert provider.get("BYBIT_API_KEY") == "chave-local-123"  # espaços removidos


def test_segredo_obrigatorio_ausente():
    provider = SecretProvider(env={})
    with pytest.raises(SecretNotFoundError, match="TELEGRAM_BOT_TOKEN"):
        provider.get("TELEGRAM_BOT_TOKEN")
    assert provider.get("TELEGRAM_BOT_TOKEN", required=False) is None


def test_segredo_vazio_conta_como_ausente():
    provider = SecretProvider(env={"BOT_INGEST_TOKEN": "   "})
    assert provider.get("BOT_INGEST_TOKEN", required=False) is None


class FakeSecretManager:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def access_secret_version(self, *, name):
        self.calls.append(name)
        secret = name.split("/")[3]
        if secret not in self.values:
            raise LookupError("NotFound")
        return SimpleNamespace(payload=SimpleNamespace(data=self.values[secret].encode()))


def test_le_do_secret_manager_com_gcp_project_e_usa_cache():
    sm = FakeSecretManager({"BYBIT_API_SECRET": "segredo-da-vm-123"})
    provider = SecretProvider(env={"GCP_PROJECT": "bybit-scanner-bot"}, sm_client=sm)
    assert provider.project == "bybit-scanner-bot"
    assert provider.get("BYBIT_API_SECRET") == "segredo-da-vm-123"
    assert provider.get("BYBIT_API_SECRET") == "segredo-da-vm-123"
    assert sm.calls == ["projects/bybit-scanner-bot/secrets/BYBIT_API_SECRET/versions/latest"]


def test_secret_manager_sem_versao_vira_ausente():
    provider = SecretProvider(env={"GCP_PROJECT": "p"}, sm_client=FakeSecretManager({}))
    with pytest.raises(SecretNotFoundError, match="Secret Manager"):
        provider.get("COINVERSA_API_KEY")


def test_log_json_tem_campos_padrao():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    get_logger("teste").info("mensagem", extra={"symbol": "BTCUSDT", "data": {"x": 1}})
    line = json.loads(stream.getvalue().strip())
    assert line["level"] == "INFO"
    assert line["component"] == "teste"
    assert line["msg"] == "mensagem"
    assert line["symbol"] == "BTCUSDT"
    assert line["data"] == {"x": 1}
    assert "ts" in line


def test_segredo_lido_nunca_aparece_no_log():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    provider = SecretProvider(env={"BYBIT_API_SECRET": "super-segredo-987"})
    value = provider.get("BYBIT_API_SECRET")
    get_logger("teste").error(f"erro com {value}", extra={"data": {"header": value}})
    try:
        raise RuntimeError(f"falhou {value}")
    except RuntimeError:
        get_logger("teste").exception("exceção")
    output = stream.getvalue()
    assert "super-segredo-987" not in output
    assert "***" in output


def test_valores_curtos_nao_sao_mascarados():
    register_secret("abc")
    stream = io.StringIO()
    setup_logging("INFO", stream)
    get_logger("teste").info("abc normal")
    assert "abc normal" in stream.getvalue()
