"""Exceções tipadas a partir do retCode da Bybit V5.

Códigos marcados com (confirmar) vêm da documentação, mas o smoke test na conta
demo registra o código real devolvido para conferência.
"""

from __future__ import annotations


class BybitError(Exception):
    def __init__(
        self,
        message: str,
        *,
        ret_code: int | None = None,
        ret_msg: str | None = None,
        endpoint: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        self.endpoint = endpoint
        self.http_status = http_status


class BybitNetworkError(BybitError):
    """Falha de rede/timeout: não se sabe se a Bybit processou o pedido."""


class BybitHTTPError(BybitError):
    """Resposta HTTP inesperada (5xx, corpo que não é JSON...)."""


class BybitAuthError(BybitError):
    """Chave inválida, assinatura errada ou chave expirada."""


class BybitIPNotAllowedError(BybitAuthError):
    """IP de origem fora da lista da chave (10010)."""


class BybitPermissionError(BybitAuthError):
    """A chave não tem permissão para esta operação (10005)."""


class BybitTimestampError(BybitError):
    """Relógio fora da janela recv_window (10002)."""


class BybitRateLimitError(BybitError):
    """Limite de requisições atingido (10006, 10018, HTTP 429/403)."""


class BybitParamError(BybitError):
    """Parâmetro inválido (10001)."""


class BybitOrderError(BybitError):
    """Erro de negócio em ordens (faixas 110xxx e 170xxx)."""


class BybitOrderNotFoundError(BybitOrderError):
    pass


class BybitDuplicateOrderError(BybitOrderError):
    """orderLinkId repetido: a ordem já existe."""


class BybitInsufficientBalanceError(BybitOrderError):
    pass


class GuardError(Exception):
    """Trava de segurança do próprio robô (nunca chega a chamar a Bybit)."""


class CategoryNotAllowedError(GuardError):
    pass


class EndpointNotAllowedError(GuardError):
    pass


TIMESTAMP_CODES = {10002}
PARAM_CODES = {10001}
AUTH_CODES = {10003, 10004, 10007, 33004}
PERMISSION_CODES = {10005}
IP_CODES = {10010}
RATE_LIMIT_CODES = {10006, 10018}
SERVER_RETRYABLE_CODES = {10016}
ORDER_NOT_FOUND_CODES = {110001, 170213}
DUPLICATE_ORDER_CODES = {110072, 170141}  # spot: 170141 confirmado na conta demo (smoke test)
INSUFFICIENT_BALANCE_CODES = {110007, 170131}


def error_from_response(
    ret_code: int, ret_msg: str, endpoint: str, http_status: int | None = None
) -> BybitError:
    """Converte um retCode != 0 na exceção mais específica."""
    message = f"Bybit retCode={ret_code} em {endpoint}: {ret_msg}"
    kwargs = {"ret_code": ret_code, "ret_msg": ret_msg, "endpoint": endpoint, "http_status": http_status}
    if ret_code in IP_CODES:
        return BybitIPNotAllowedError(message + " (IP fora da lista da chave)", **kwargs)
    if ret_code in PERMISSION_CODES:
        return BybitPermissionError(message, **kwargs)
    if ret_code in AUTH_CODES:
        return BybitAuthError(message, **kwargs)
    if ret_code in TIMESTAMP_CODES:
        return BybitTimestampError(message, **kwargs)
    if ret_code in RATE_LIMIT_CODES:
        return BybitRateLimitError(message, **kwargs)
    if ret_code in PARAM_CODES:
        return BybitParamError(message, **kwargs)
    if ret_code in ORDER_NOT_FOUND_CODES:
        return BybitOrderNotFoundError(message, **kwargs)
    if ret_code in DUPLICATE_ORDER_CODES:
        return BybitDuplicateOrderError(message, **kwargs)
    if ret_code in INSUFFICIENT_BALANCE_CODES:
        return BybitInsufficientBalanceError(message, **kwargs)
    if 110000 <= ret_code < 111000 or 170000 <= ret_code < 171000:
        return BybitOrderError(message, **kwargs)
    return BybitError(message, **kwargs)
