"""Logs estruturados em JSON, com mascaramento de segredos.

Uso:
    log = get_logger("bybit.client")
    log.info("ordem criada", extra={"symbol": "BTCUSDT", "data": {"orderLinkId": "..."}})

Todo valor registrado com register_secret() é trocado por "***" em qualquer
linha de log, mesmo que apareça por engano numa mensagem ou exceção.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import UTC, datetime
from typing import IO

_MASK = "***"
_MIN_SECRET_LEN = 6
_secrets: set[str] = set()
_lock = threading.Lock()


def register_secret(value: str | None) -> None:
    """Registra um segredo para nunca aparecer nos logs."""
    if value and len(value) >= _MIN_SECRET_LEN:
        with _lock:
            _secrets.add(value)


def redact(text: str) -> str:
    with _lock:
        secrets = sorted(_secrets, key=len, reverse=True)
    for secret in secrets:
        if secret in text:
            text = text.replace(secret, _MASK)
    return text


class JsonFormatter(logging.Formatter):
    """Uma linha JSON por evento: ts, level, component, msg, symbol, data, exc."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "component": record.name.removeprefix("bot."),
            "msg": record.getMessage(),
        }
        symbol = getattr(record, "symbol", None)
        if symbol is not None:
            payload["symbol"] = symbol
        data = getattr(record, "data", None)
        if data is not None:
            payload["data"] = data
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, ensure_ascii=False, default=str))


def setup_logging(level: str = "INFO", stream: IO[str] | None = None) -> None:
    """Configura o logger raiz do robô ("bot") para emitir JSON."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("bot")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    # bibliotecas de rede não devem despejar URLs/headers em DEBUG
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(f"bot.{component}")
