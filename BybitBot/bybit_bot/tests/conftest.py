from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from bot.bybit.client import BybitClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT.parent / "config.example.yaml"

API_KEY = "testkey123456"
API_SECRET = "testsecret123456789"
SERVER_TIME_MS = 1_700_000_000_000


def ok(result: dict | None = None, **extra) -> dict:
    return {"retCode": 0, "retMsg": "OK", "result": result or {}, "retExtInfo": {}, "time": SERVER_TIME_MS,
            **extra}


def err(code: int, msg: str = "erro") -> dict:
    return {"retCode": code, "retMsg": msg, "result": {}, "retExtInfo": {}, "time": SERVER_TIME_MS}


def time_response() -> dict:
    return ok({"timeSecond": str(SERVER_TIME_MS // 1000), "timeNano": str(SERVER_TIME_MS * 1_000_000)})


class FakeBybit:
    """Servidor falso: cada rota tem uma fila de respostas; a última se repete."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], list] = {("GET", "/v5/market/time"): [time_response()]}
        self.requests: list[httpx.Request] = []

    def on(self, method: str, path: str, *responses) -> FakeBybit:
        self.routes[(method, path)] = list(responses)
        return self

    def calls(self, method: str, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and r.url.path == path]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key not in self.routes:
            return httpx.Response(404, text="rota não simulada")
        queue = self.routes[key]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        if isinstance(item, Callable):
            item = item(request)
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json=item)


@pytest.fixture
def fake() -> FakeBybit:
    return FakeBybit()


class FakeClock:
    def __init__(self, start: float = SERVER_TIME_MS / 1000) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_client(fake: FakeBybit, clock: FakeClock):
    def _make(**kwargs) -> BybitClient:
        params = dict(
            api_key=API_KEY,
            api_secret=API_SECRET,
            recv_window_ms=5000,
            max_requests_per_second=1000,
            max_retries=3,
            backoff_base_seconds=0.5,
            backoff_max_seconds=8,
            http_client=httpx.Client(transport=httpx.MockTransport(fake.handler)),
            clock=clock.time,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
            rng=lambda: 1.0,
        )
        params.update(kwargs)
        return BybitClient("https://api-demo.bybit.com", **params)

    return _make


def query_of(request: httpx.Request) -> str:
    return urlsplit(str(request.url)).query


def params_of(request: httpx.Request) -> dict[str, str]:
    return dict(parse_qsl(query_of(request)))


def body_of(request: httpx.Request) -> dict:
    return json.loads(request.content.decode())
