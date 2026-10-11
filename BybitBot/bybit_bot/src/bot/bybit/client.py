"""Cliente REST da Bybit V5 (assinatura própria com httpx).

Travas de segurança, verificadas ANTES de qualquer chamada:
- só a categoria "spot" é aceita (o projeto opera sem alavancagem);
- só os endpoints privados da lista PRIVATE_ENDPOINTS podem ser chamados:
  não existe caminho para saque, transferência, alavancagem ou posições.

Retentativas:
- leitura (GET) e cancelamento: novas tentativas em rede/5xx/limite/horário;
- criação de ordem: nunca reenvia às cegas. Em falha ambígua (rede ou 5xx)
  procura a ordem pelo orderLinkId antes de reenviar; orderLinkId repetido
  devolve a ordem que já existe.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlencode

import httpx

from bot.bybit.errors import (
    SERVER_RETRYABLE_CODES,
    BybitDuplicateOrderError,
    BybitError,
    BybitHTTPError,
    BybitNetworkError,
    BybitRateLimitError,
    BybitTimestampError,
    CategoryNotAllowedError,
    EndpointNotAllowedError,
    error_from_response,
)
from bot.logging_setup import get_logger

ALLOWED_CATEGORIES = frozenset({"spot"})

PRIVATE_ENDPOINTS = frozenset(
    {
        ("GET", "/v5/account/wallet-balance"),
        ("GET", "/v5/user/query-api"),
        ("POST", "/v5/order/create"),
        ("POST", "/v5/order/cancel"),
        ("GET", "/v5/order/realtime"),
        ("GET", "/v5/order/history"),
        ("GET", "/v5/execution/list"),
    }
)

KLINE_INTERVAL_MS = {
    "1": 60_000,
    "3": 180_000,
    "5": 300_000,
    "15": 900_000,
    "30": 1_800_000,
    "60": 3_600_000,
    "120": 7_200_000,
    "240": 14_400_000,
    "360": 21_600_000,
    "720": 43_200_000,
    "D": 86_400_000,
    "W": 604_800_000,
}

OPEN_ORDER_STATUSES = frozenset({"New", "PartiallyFilled", "Untriggered"})

MAX_PAGES = 50
USER_AGENT = "bybit-scanner-bot/0.1"

RetryPolicy = Literal["safe", "order_create"]

log = get_logger("bybit.client")


@dataclass(frozen=True)
class Kline:
    start_ms: int
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float

    @property
    def end_ms(self) -> int:
        return self.start_ms + KLINE_INTERVAL_MS[self.interval]

    def is_closed(self, now_ms: int) -> bool:
        """Vela fechada: o período inteiro já passou. Sinais só usam velas fechadas."""
        return self.end_ms <= now_ms


@dataclass
class RateLimitStatus:
    limit: int | None = None
    remaining: int | None = None
    reset_ms: int | None = None


class RateLimiter:
    """Espaça as chamadas para no máximo `max_per_second` por segundo."""

    def __init__(
        self,
        max_per_second: float,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = 1.0 / max_per_second
        self._monotonic = monotonic
        self._sleep = sleep
        self._next_at = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._monotonic()
            wait = self._next_at - now
            if wait > 0:
                self._sleep(wait)
                now += wait
            self._next_at = now + self._interval


def sign_payload(api_secret: str, timestamp_ms: int, api_key: str, recv_window_ms: int, payload: str) -> str:
    """Assinatura V5: HMAC-SHA256(secret, timestamp + apiKey + recvWindow + payload) em hex."""
    message = f"{timestamp_ms}{api_key}{recv_window_ms}{payload}"
    return hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def build_query(params: dict[str, Any] | None) -> str:
    """Query string na ordem dada, sem valores None. É exatamente o que é assinado e enviado."""
    if not params:
        return ""
    return urlencode([(k, _to_str(v)) for k, v in params.items() if v is not None])


def _to_str(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


class BybitClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        api_secret: str | None = None,
        *,
        recv_window_ms: int = 5000,
        max_requests_per_second: float = 8,
        timeout_seconds: float = 10,
        max_retries: int = 4,
        backoff_base_seconds: float = 0.5,
        backoff_max_seconds: float = 8,
        time_sync_minutes: float = 30,
        http_client: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self.recv_window_ms = recv_window_ms
        self.max_retries = max_retries
        self.backoff_base = backoff_base_seconds
        self.backoff_max = backoff_max_seconds
        self.time_sync_seconds = time_sync_minutes * 60
        self._http = http_client or httpx.Client(timeout=timeout_seconds, headers={"User-Agent": USER_AGENT})
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._rng = rng
        self._limiter = RateLimiter(max_requests_per_second, monotonic, sleep)
        self._time_offset_ms = 0.0
        self._last_sync: float | None = None
        self.rate_limit = RateLimitStatus()

    # ------------------------------------------------------------------ fábrica
    @classmethod
    def from_config(cls, config: Any, secrets: Any | None, mode: str | None = None) -> BybitClient:
        """Cria o cliente a partir do BotConfig. Em paper, sem chave (só dados públicos)."""
        mode = mode or config.mode
        b = config.bybit
        api_key = api_secret = None
        if mode in ("demo", "live"):
            if mode == "live":
                from bot.config import ensure_live_allowed

                ensure_live_allowed(config)
            api_key = secrets.get("BYBIT_API_KEY")
            api_secret = secrets.get("BYBIT_API_SECRET")
        return cls(
            config.rest_url_for(mode),
            api_key,
            api_secret,
            recv_window_ms=b.recv_window_ms,
            max_requests_per_second=b.max_requests_per_second,
            timeout_seconds=b.http_timeout_seconds,
            max_retries=b.max_retries,
            backoff_base_seconds=b.backoff_base_seconds,
            backoff_max_seconds=b.backoff_max_seconds,
            time_sync_minutes=b.time_sync_minutes,
        )

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ horário
    @property
    def time_offset_ms(self) -> float:
        return self._time_offset_ms

    def sync_time(self) -> float:
        """Mede a diferença entre o relógio local e o da Bybit (meio do round-trip)."""
        t0 = self._clock()
        data = self._request("GET", "/v5/market/time", sync_clock=False)
        t1 = self._clock()
        result = data.get("result") or {}
        if result.get("timeNano"):
            server_ms = int(result["timeNano"]) // 1_000_000
        elif result.get("timeSecond"):
            server_ms = int(result["timeSecond"]) * 1000
        else:
            server_ms = int(data["time"])
        self._time_offset_ms = server_ms - (t0 + t1) / 2 * 1000
        self._last_sync = self._monotonic()
        log.info("relógio sincronizado com a Bybit", extra={"data": {"offset_ms": round(self._time_offset_ms)}})
        return self._time_offset_ms

    def now_ms(self) -> int:
        """Horário estimado da Bybit em ms."""
        return int(self._clock() * 1000 + self._time_offset_ms)

    def _signed_timestamp(self) -> int:
        stale = self._last_sync is None or self._monotonic() - self._last_sync > self.time_sync_seconds
        if stale:
            self.sync_time()
        return self.now_ms()

    # ------------------------------------------------------------------ núcleo
    def _check_guards(self, method: str, path: str, params: dict | None, body: dict | None, signed: bool):
        if signed and (method, path) not in PRIVATE_ENDPOINTS:
            raise EndpointNotAllowedError(f"endpoint privado não permitido pelo robô: {method} {path}")
        for source in (params, body):
            category = (source or {}).get("category")
            if category is not None and category not in ALLOWED_CATEGORIES:
                raise CategoryNotAllowedError(
                    f"categoria '{category}' recusada: o robô opera só spot (sem derivativos)"
                )

    def _backoff(self, attempt: int) -> float:
        delay = min(self.backoff_max, self.backoff_base * (2**attempt))
        return delay * (0.5 + self._rng() / 2)

    def _respect_rate_limit_headers(self) -> None:
        rl = self.rate_limit
        if rl.remaining is not None and rl.remaining <= 0 and rl.reset_ms:
            wait = (rl.reset_ms - self.now_ms()) / 1000
            if wait > 0:
                wait = min(wait, self.backoff_max)
                log.warning("limite de requisições esgotado, aguardando reset", extra={"data": {"wait_s": wait}})
                self._sleep(wait)

    def _update_rate_limit(self, headers: httpx.Headers) -> None:
        def _int(name: str) -> int | None:
            value = headers.get(name)
            try:
                return int(value) if value is not None else None
            except ValueError:
                return None

        status = _int("X-Bapi-Limit-Status")
        if status is not None:
            self.rate_limit = RateLimitStatus(
                limit=_int("X-Bapi-Limit"),
                remaining=status,
                reset_ms=_int("X-Bapi-Limit-Reset-Timestamp"),
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        signed: bool = False,
        retry: RetryPolicy = "safe",
        sync_clock: bool = True,
    ) -> dict[str, Any]:
        method = method.upper()
        self._check_guards(method, path, params, body, signed)
        if signed and not (self._api_key and self._api_secret):
            raise BybitError(f"chamada privada {path} sem chave de API configurada", endpoint=path)

        query = build_query(params)
        body_text = json.dumps({k: v for k, v in (body or {}).items() if v is not None}, separators=(",", ":"))
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        resynced = False
        attempt = 0

        while True:
            self._limiter.acquire()
            self._respect_rate_limit_headers()
            headers = {"Content-Type": "application/json"} if method == "POST" else {}
            if signed:
                ts = self._signed_timestamp() if sync_clock else self.now_ms()
                payload = body_text if method == "POST" else query
                headers.update(
                    {
                        "X-BAPI-API-KEY": self._api_key,
                        "X-BAPI-TIMESTAMP": str(ts),
                        "X-BAPI-RECV-WINDOW": str(self.recv_window_ms),
                        "X-BAPI-SIGN": sign_payload(self._api_secret, ts, self._api_key, self.recv_window_ms,
                                                    payload),
                    }
                )

            try:
                response = self._http.request(
                    method, url, headers=headers, content=body_text if method == "POST" else None
                )
            except httpx.HTTPError as exc:
                err = BybitNetworkError(f"falha de rede em {path}: {type(exc).__name__}", endpoint=path)
                if retry == "safe" and attempt < self.max_retries:
                    self._sleep_retry(attempt, path, err)
                    attempt += 1
                    continue
                raise err from exc

            self._update_rate_limit(response.headers)

            # 429 e 403 da Bybit = limite por IP (o pedido não foi processado); 403 também aparece
            # para IPs dos EUA. Seguro repetir com espera, inclusive na criação de ordem.
            if response.status_code in (403, 429):
                err = BybitRateLimitError(
                    f"HTTP {response.status_code} em {path} (limite de requisições ou IP bloqueado)",
                    endpoint=path,
                    http_status=response.status_code,
                )
                if attempt < self.max_retries:
                    self._sleep_retry(attempt, path, err)
                    attempt += 1
                    continue
                raise err

            if response.status_code >= 500:
                err = BybitHTTPError(f"HTTP {response.status_code} em {path}", endpoint=path,
                                     http_status=response.status_code)
                if retry == "safe" and attempt < self.max_retries:
                    self._sleep_retry(attempt, path, err)
                    attempt += 1
                    continue
                raise err

            try:
                data = response.json()
            except ValueError as exc:
                raise BybitHTTPError(
                    f"resposta não-JSON em {path} (HTTP {response.status_code})",
                    endpoint=path,
                    http_status=response.status_code,
                ) from exc

            ret_code = data.get("retCode")
            if ret_code == 0:
                return data
            if ret_code is None:
                raise BybitHTTPError(f"resposta sem retCode em {path}", endpoint=path,
                                     http_status=response.status_code)

            err = error_from_response(int(ret_code), str(data.get("retMsg", "")), path, response.status_code)
            if isinstance(err, BybitTimestampError) and signed and not resynced:
                # pedido recusado antes de processar: seguro ressincronizar e repetir
                log.warning("timestamp recusado, ressincronizando relógio", extra={"data": {"path": path}})
                self.sync_time()
                resynced = True
                continue
            if isinstance(err, BybitRateLimitError) and attempt < self.max_retries:
                self._sleep_retry(attempt, path, err)
                attempt += 1
                continue
            if err.ret_code in SERVER_RETRYABLE_CODES and retry == "safe" and attempt < self.max_retries:
                self._sleep_retry(attempt, path, err)
                attempt += 1
                continue
            raise err

    def _sleep_retry(self, attempt: int, path: str, err: Exception) -> None:
        delay = self._backoff(attempt)
        log.warning(
            "erro temporário, nova tentativa",
            extra={"data": {"path": path, "attempt": attempt + 1, "wait_s": round(delay, 2),
                            "error": str(err)}},
        )
        self._sleep(delay)

    def _paginate(self, path: str, params: dict[str, Any], *, signed: bool, max_pages: int = MAX_PAGES
                  ) -> Iterator[dict[str, Any]]:
        cursor: str | None = None
        for _ in range(max_pages):
            page_params = dict(params)
            if cursor:
                page_params["cursor"] = cursor
            data = self._request("GET", path, params=page_params, signed=signed)
            result = data.get("result") or {}
            yield from result.get("list") or []
            cursor = result.get("nextPageCursor") or None
            if not cursor:
                return
        log.warning("paginação interrompida no limite de páginas", extra={"data": {"path": path}})

    # ------------------------------------------------------------------ dados públicos
    def get_server_time_ms(self) -> int:
        data = self._request("GET", "/v5/market/time", sync_clock=False)
        return int(data["result"]["timeNano"]) // 1_000_000

    def get_instruments_info(self, symbol: str | None = None, category: str = "spot") -> list[dict[str, Any]]:
        params = {"category": category, "symbol": symbol}
        return list(self._paginate("/v5/market/instruments-info", params, signed=False))

    def get_tickers(self, symbol: str | None = None, category: str = "spot") -> list[dict[str, Any]]:
        data = self._request("GET", "/v5/market/tickers", params={"category": category, "symbol": symbol})
        return (data.get("result") or {}).get("list") or []

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_ms: int | None = None,
        end_ms: int | None = None,
        category: str = "spot",
    ) -> list[Kline]:
        """Velas em ordem cronológica (a Bybit devolve da mais nova para a mais velha)."""
        if interval not in KLINE_INTERVAL_MS:
            raise ValueError(f"intervalo de vela não suportado: {interval}")
        if not 1 <= limit <= 1000:
            raise ValueError("limit deve estar entre 1 e 1000")
        params = {"category": category, "symbol": symbol, "interval": interval, "start": start_ms,
                  "end": end_ms, "limit": limit}
        data = self._request("GET", "/v5/market/kline", params=params)
        rows = (data.get("result") or {}).get("list") or []
        klines = [
            Kline(int(r[0]), interval, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]),
                  float(r[6]))
            for r in rows
        ]
        return sorted(klines, key=lambda k: k.start_ms)

    # ------------------------------------------------------------------ conta
    def get_api_key_info(self) -> dict[str, Any]:
        """Permissões, IPs e status da chave em uso (só leitura)."""
        return self._request("GET", "/v5/user/query-api", signed=True)["result"]

    def get_wallet_balance(self, account_type: str = "UNIFIED", coin: str | None = None) -> dict[str, Any]:
        data = self._request("GET", "/v5/account/wallet-balance",
                             params={"accountType": account_type, "coin": coin}, signed=True)
        accounts = (data.get("result") or {}).get("list") or []
        return accounts[0] if accounts else {}

    # ------------------------------------------------------------------ ordens
    def place_order(
        self,
        *,
        symbol: str,
        side: Literal["Buy", "Sell"],
        order_type: Literal["Limit", "Market"],
        qty: str | Decimal,
        order_link_id: str,
        price: str | Decimal | None = None,
        time_in_force: str | None = None,
        market_unit: Literal["baseCoin", "quoteCoin"] | None = None,
        category: str = "spot",
    ) -> dict[str, Any]:
        """Cria ordem de forma idempotente pelo orderLinkId. Devolve {orderId, orderLinkId}."""
        if side not in ("Buy", "Sell"):
            raise ValueError(f"side inválido: {side}")
        if order_type not in ("Limit", "Market"):
            raise ValueError(f"orderType inválido: {order_type}")
        if order_type == "Limit" and price is None:
            raise ValueError("ordem Limit exige price")
        if not order_link_id or len(order_link_id) > 36:
            raise ValueError("orderLinkId é obrigatório e tem no máximo 36 caracteres")
        body = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": _to_str(qty),
            "price": _to_str(price) if price is not None else None,
            "timeInForce": time_in_force or ("GTC" if order_type == "Limit" else "IOC"),
            "marketUnit": market_unit,
            "orderLinkId": order_link_id,
        }
        for attempt in range(self.max_retries + 1):
            try:
                data = self._request("POST", "/v5/order/create", body=body, signed=True, retry="order_create")
                result = data["result"]
                log.info("ordem criada", extra={"symbol": symbol, "data": {
                    "side": side, "type": order_type, "qty": body["qty"], "price": body["price"],
                    "orderLinkId": order_link_id, "orderId": result.get("orderId")}})
                return result
            except BybitDuplicateOrderError:
                existing = self.find_order(symbol, order_link_id, category)
                if existing:
                    log.warning("orderLinkId já existia, usando a ordem existente",
                                extra={"symbol": symbol, "data": {"orderLinkId": order_link_id}})
                    return {"orderId": existing.get("orderId"), "orderLinkId": order_link_id}
                raise
            except (BybitNetworkError, BybitHTTPError) as exc:
                # Resultado ambíguo: a ordem pode ter sido criada. Procura antes de reenviar.
                existing = self.find_order(symbol, order_link_id, category)
                if existing:
                    log.warning("ordem encontrada após falha ambígua",
                                extra={"symbol": symbol, "data": {"orderLinkId": order_link_id}})
                    return {"orderId": existing.get("orderId"), "orderLinkId": order_link_id}
                if attempt >= self.max_retries:
                    raise
                self._sleep_retry(attempt, "/v5/order/create", exc)
        raise AssertionError("inalcançável")

    def find_order(self, symbol: str, order_link_id: str, category: str = "spot") -> dict[str, Any] | None:
        """Procura a ordem pelo orderLinkId em qualquer status (aberta, recém-fechada ou no histórico)."""
        recent = self.get_realtime_orders(symbol=symbol, order_link_id=order_link_id, category=category)
        if recent:
            return recent[0]
        history = self.get_order_history(symbol=symbol, order_link_id=order_link_id, category=category)
        return history[0] if history else None

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
        category: str = "spot",
    ) -> dict[str, Any]:
        if not (order_id or order_link_id):
            raise ValueError("informe order_id ou order_link_id")
        body = {"category": category, "symbol": symbol, "orderId": order_id, "orderLinkId": order_link_id}
        data = self._request("POST", "/v5/order/cancel", body=body, signed=True)
        log.info("ordem cancelada", extra={"symbol": symbol, "data": {"orderId": order_id,
                                                                      "orderLinkId": order_link_id}})
        return data["result"]

    def get_realtime_orders(
        self,
        symbol: str | None = None,
        order_link_id: str | None = None,
        category: str = "spot",
    ) -> list[dict[str, Any]]:
        """Resposta crua de /v5/order/realtime. Consultando por orderLinkId, a Bybit também devolve
        ordens fechadas nos últimos ~10 minutos (confirmado na conta demo)."""
        params = {"category": category, "symbol": symbol, "orderLinkId": order_link_id, "openOnly": 0,
                  "limit": 50}
        return list(self._paginate("/v5/order/realtime", params, signed=True))

    def get_open_orders(
        self,
        symbol: str | None = None,
        order_link_id: str | None = None,
        category: str = "spot",
    ) -> list[dict[str, Any]]:
        """Só ordens realmente abertas (New, PartiallyFilled, Untriggered)."""
        orders = self.get_realtime_orders(symbol=symbol, order_link_id=order_link_id, category=category)
        return [o for o in orders if o.get("orderStatus") in OPEN_ORDER_STATUSES]

    def get_order_history(
        self,
        symbol: str | None = None,
        order_link_id: str | None = None,
        limit: int = 50,
        category: str = "spot",
    ) -> list[dict[str, Any]]:
        params = {"category": category, "symbol": symbol, "orderLinkId": order_link_id, "limit": limit}
        data = self._request("GET", "/v5/order/history", params=params, signed=True)
        return (data.get("result") or {}).get("list") or []

    def get_executions(
        self,
        symbol: str | None = None,
        order_link_id: str | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 50,
        category: str = "spot",
        max_pages: int = MAX_PAGES,
    ) -> list[dict[str, Any]]:
        params = {"category": category, "symbol": symbol, "orderLinkId": order_link_id, "startTime": start_ms,
                  "endTime": end_ms, "limit": limit}
        return list(self._paginate("/v5/execution/list", params, signed=True, max_pages=max_pages))
