"""Envio de eventos ao painel (endpoint bot-ingest), conforme 05_DASHBOARD_E_INTEGRACAO.md.

Nunca levanta exceção nem trava o robô. Política por resposta:
- 200: ok
- 400 / 401: erro de contrato ou token -> não repete (requeue=False)
- 409 reason=not_found -> reenfileirar depois; reason=closed -> descartar
- 429, 503, 5xx, falha de rede -> repete com espera; se esgotar, requeue=True
O Cloudflare do painel recusa requisições sem User-Agent (403, código 1010).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from bot.logging_setup import get_logger

USER_AGENT = "bybit-scanner-bot/0.1"
log = get_logger("reporting.dashboard")


@dataclass(frozen=True)
class SendResult:
    ok: bool
    status: int | None = None
    body: dict[str, Any] | None = None
    requeue: bool = False


def clean_json(value: Any) -> Any:
    """Troca NaN/infinito por None (JSON padrão não aceita NaN)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: clean_json(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [clean_json(v) for v in value]
    return value


class DashboardClient:
    def __init__(
        self,
        ingest_url: str,
        token: str,
        timeout_seconds: float = 15,
        max_retries: int = 3,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.url = ingest_url
        self._headers = {"x-bot-token": token, "Content-Type": "application/json", "User-Agent": USER_AGENT}
        self._http = http_client or httpx.Client(timeout=timeout_seconds)
        self._max_retries = max_retries
        self._sleep = sleep

    @classmethod
    def from_config(cls, config: Any, secrets: Any) -> DashboardClient | None:
        if not config.dashboard.enabled:
            return None
        d = config.dashboard
        return cls(d.ingest_url, secrets.get("BOT_INGEST_TOKEN"), d.timeout_seconds, d.max_retries)

    def close(self) -> None:
        self._http.close()

    def send(self, type_: str, payload: dict[str, Any]) -> SendResult:
        body = {"type": type_, "payload": clean_json(payload)}
        last_status = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._http.post(self.url, headers=self._headers, json=body)
            except httpx.HTTPError as exc:
                log.warning("painel inacessível", extra={"data": {"type": type_, "attempt": attempt + 1,
                                                                  "error": type(exc).__name__}})
                if attempt < self._max_retries:
                    self._sleep(2**attempt)
                continue
            last_status = response.status_code
            data = _json(response)
            if response.status_code == 200:
                return SendResult(True, 200, data)
            if response.status_code in (400, 401, 403):
                log.error("painel recusou o envio (não será repetido)",
                          extra={"data": {"type": type_, "status": response.status_code,
                                          "resposta": response.text[:300]}})
                return SendResult(False, response.status_code, data)
            if response.status_code == 409:
                reason = (data or {}).get("reason")
                return SendResult(False, 409, data, requeue=reason == "not_found")
            log.warning("erro temporário do painel", extra={"data": {"type": type_, "status": response.status_code,
                                                                     "attempt": attempt + 1}})
            if attempt < self._max_retries:
                self._sleep(2**attempt)
        return SendResult(False, last_status, None, requeue=True)


def _json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
