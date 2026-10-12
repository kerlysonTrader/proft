"""Leitura de segredos.

- Com a variável GCP_PROJECT definida (na VM): Google Secret Manager, versão "latest".
  No PC (sem a biblioteca google-cloud-secret-manager) lê pelo gcloud já logado do usuário:
  `gcloud secrets versions access latest` — o valor nunca é mostrado nem gravado.
- Sem GCP_PROJECT (desenvolvimento local): variáveis de ambiente / arquivo .env.

Todo segredo lido é registrado para mascaramento nos logs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from bot.logging_setup import get_logger, register_secret

SECRET_NAMES = (
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "BOT_INGEST_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "GEMINI_API_KEY",
    "COINVERSA_API_KEY",
)

log = get_logger("secrets")


class SecretNotFoundError(Exception):
    """Segredo obrigatório ausente ou vazio."""


class SecretManagerLike(Protocol):
    def access_secret_version(self, *, name: str) -> Any: ...


class SecretProvider:
    def __init__(
        self,
        project: str | None = None,
        env: Mapping[str, str] | None = None,
        sm_client: SecretManagerLike | None = None,
        gcloud_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    ) -> None:
        self._env = os.environ if env is None else env
        self.project = project if project is not None else self._env.get("GCP_PROJECT") or None
        self._sm_client = sm_client
        self._gcloud_runner = gcloud_runner
        self._cache: dict[str, str | None] = {}
        self._lock = threading.Lock()

    @property
    def source(self) -> str:
        return f"Secret Manager ({self.project})" if self.project else "variáveis de ambiente"

    def get(self, name: str, required: bool = True) -> str | None:
        with self._lock:
            if name not in self._cache:
                value = self._read_secret_manager(name) if self.project else self._env.get(name)
                value = value.strip() if value else None
                self._cache[name] = value or None
                register_secret(self._cache[name])
            value = self._cache[name]
        if value is None and required:
            raise SecretNotFoundError(f"segredo {name} não encontrado em {self.source}")
        return value

    def _client(self) -> SecretManagerLike:
        if self._sm_client is None:
            from google.cloud import secretmanager  # importado só na VM (extra "gcp")

            self._sm_client = secretmanager.SecretManagerServiceClient()
        return self._sm_client

    def _read_secret_manager(self, name: str) -> str | None:
        path = f"projects/{self.project}/secrets/{name}/versions/latest"
        try:
            client = self._client()
        except ImportError:  # PC sem a biblioteca: usa o gcloud do usuário
            return self._read_gcloud(name)
        try:
            response = client.access_secret_version(name=path)
        except Exception as exc:  # NotFound, FailedPrecondition (sem versão ativa), PermissionDenied...
            log.warning("segredo indisponível no Secret Manager",
                        extra={"data": {"secret": name, "error": type(exc).__name__}})
            return None
        return response.payload.data.decode("utf-8")

    def _read_gcloud(self, name: str) -> str | None:
        args = ["secrets", "versions", "access", "latest", f"--secret={name}", f"--project={self.project}"]
        try:
            if self._gcloud_runner is not None:
                result = self._gcloud_runner(args)
            else:
                exe = gcloud_executable()
                if exe is None:
                    log.warning("gcloud não encontrado para ler o segredo", extra={"data": {"secret": name}})
                    return None
                result = subprocess.run([exe, *args], capture_output=True, text=True, timeout=90, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("falha ao chamar o gcloud", extra={"data": {"secret": name, "error": type(exc).__name__}})
            return None
        if result.returncode != 0:
            log.warning("segredo indisponível pelo gcloud",
                        extra={"data": {"secret": name, "returncode": result.returncode}})
            return None
        return result.stdout


def gcloud_executable() -> str | None:
    found = shutil.which("gcloud")
    if found:
        return found
    sdk = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Cloud SDK" / "google-cloud-sdk"
    local = sdk / "bin" / "gcloud.cmd"
    return str(local) if local.exists() else None


def load_dotenv_if_local() -> None:
    """Carrega .env só no desenvolvimento local (sem GCP_PROJECT)."""
    if os.environ.get("GCP_PROJECT"):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)
