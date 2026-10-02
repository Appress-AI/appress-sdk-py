from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from appress import Appress, AsyncAppress, _http

Responder = Callable[[httpx.Request], httpx.Response]


class Recorder:
    """Mock transport: returns the given responses in order (the last one repeats) and records requests."""

    def __init__(self, *responders: Responder) -> None:
        self.responders = responders
        self.requests: list[httpx.Request] = []
        self.bodies: list[bytes] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.bodies.append(request.read())
        responder = self.responders[min(len(self.requests) - 1, len(self.responders) - 1)]
        return responder(request)

    def json(self, index: int = -1) -> Any:
        return json.loads(self.bodies[index])


def ok(data: Any, status: int = 200, headers: dict[str, str] | None = None) -> Responder:
    return lambda _: httpx.Response(status, json={"success": True, "data": data}, headers=headers)


def fail(status: int, message: str, code: str | None = None, headers: dict[str, str] | None = None) -> Responder:
    body: dict[str, Any] = {"success": False, "statusCode": status, "message": message}
    if code:
        body["code"] = code
    return lambda _: httpx.Response(status, json=body, headers=headers)


def network_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def client(recorder: Recorder, **options: Any) -> Appress:
    settings: dict[str, Any] = {"api_key": "apr_live_test", "base_url": "https://api.test", **options}
    return Appress(http_client=httpx.Client(transport=httpx.MockTransport(recorder)), **settings)


def async_client(recorder: Recorder, **options: Any) -> AsyncAppress:
    settings: dict[str, Any] = {"api_key": "apr_live_test", "base_url": "https://api.test", **options}
    return AsyncAppress(http_client=httpx.AsyncClient(transport=httpx.MockTransport(recorder)), **settings)


def generation(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "3cf8a05e-662c-4f18-abd5-14f5c1a5f91d",
        "featureType": "NEWS",
        "inputType": "TEXT",
        "status": "PENDING",
        "title": None,
        "progress": {"step": None, "percent": None},
        "estimatedCostUsd": "0.200000",
        "actualCostUsd": None,
        "createdAt": "2026-10-01T09:00:00.000Z",
        "updatedAt": "2026-10-01T09:00:00.000Z",
        **overrides,
    }


def live_session(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "9b1f7d2a-1111-4c22-8a33-000000000001",
        "url": "https://www.youtube.com/watch?v=x",
        "generationId": "9b1f7d2a-1111-4c22-8a33-000000000002",
        "state": "STREAMING",
        "platform": "youtube",
        "expectedLanguage": "tr",
        "maxDurationMinutes": 120,
        "expiresAt": None,
        "lastSequence": 0,
        "mediaTitle": None,
        "failureCode": None,
        "failureMessage": None,
        "turns": [],
        "createdAt": "2026-10-01T09:00:00.000Z",
        "startedAt": None,
        "completedAt": None,
        "reservedCostUsd": "1.000000",
        **overrides,
    }


def turn(turn_id: str, text: str, is_final: bool, sequence: int = 1) -> dict[str, Any]:
    return {
        "turnId": turn_id,
        "sequence": sequence,
        "text": text,
        "isFinal": is_final,
        "startMs": None,
        "endMs": None,
        "speaker": None,
        "language": None,
        "words": None,
    }


@pytest.fixture(autouse=True)
def sleeps(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[float]]:
    """Records every sleep instead of waiting."""
    recorded: list[float] = []

    def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    async def fake_async_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(_http, "sleep", fake_sleep)
    monkeypatch.setattr(_http, "async_sleep", fake_async_sleep)
    yield recorded
