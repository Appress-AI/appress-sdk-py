"""Request engine: ``{success, data}`` unwrap, error mapping, retries and timeouts."""

from __future__ import annotations

import asyncio
import json
import platform
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from ._errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    create_api_error,
    parse_retry_after_seconds,
)
from ._files import Upload
from ._version import __version__

DEFAULT_BASE_URL = "https://api.appress.ai"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 4
#: Default timeout for file uploads: large audio files can take minutes.
UPLOAD_TIMEOUT = 30 * 60.0

RETRYABLE_STATUS = frozenset({408, 429, 502, 503, 504})
INITIAL_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 16.0
MAX_RETRY_AFTER = 60.0

USER_AGENT = f"appress-sdk-python/{__version__} python/{platform.python_version()}"

# Module-level so tests can replace them; resources use them for polling too.
sleep = time.sleep
async_sleep = asyncio.sleep


@dataclass
class Request:
    method: str
    path: str
    query: Mapping[str, Any] | None = None
    json: Any = None
    #: Multipart form fields; sent together with ``upload``.
    form: Mapping[str, str] | None = None
    upload: Upload | None = None
    idempotency_key: str | None = None
    timeout: float | None = None
    max_retries: int | None = None
    headers: Mapping[str, str] = field(default_factory=dict)


class _Base:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float,
        max_retries: int,
        default_headers: Mapping[str, str],
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_headers = dict(default_headers)

    def _build(self, req: Request) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": USER_AGENT,
            **self.default_headers,
            **req.headers,
        }
        # Every attempt of one logical request sends the same key, so the server
        # treats a retry as a replay of the first attempt and never charges twice.
        if req.idempotency_key:
            headers["Idempotency-Key"] = req.idempotency_key

        kwargs: dict[str, Any] = {
            "method": req.method,
            "url": self.base_url.rstrip("/") + "/" + req.path.lstrip("/"),
            "headers": headers,
            "timeout": req.timeout if req.timeout is not None else self.timeout,
        }
        if req.query:
            kwargs["params"] = {key: _query_value(value) for key, value in req.query.items() if value is not None}
        if req.upload is not None:
            kwargs["data"] = dict(req.form or {})
            kwargs["files"] = {"file": req.upload.part()}
        elif req.json is not None:
            kwargs["json"] = req.json
        return kwargs

    def _max_retries(self, req: Request) -> int:
        return req.max_retries if req.max_retries is not None else self.max_retries


class SyncHTTP(_Base):
    def __init__(self, *, client: httpx.Client | None, **options: Any) -> None:
        super().__init__(**options)
        self._owns_client = client is None
        self.client = client or httpx.Client()

    def request(self, req: Request) -> Any:
        max_retries = self._max_retries(req)
        attempt = 0
        try:
            while True:
                try:
                    return self._send(req)
                except (APIError, APIConnectionError) as error:
                    if attempt >= max_retries or not is_retryable(error):
                        raise
                    sleep(retry_delay(error, attempt))
                    attempt += 1
        finally:
            if req.upload is not None:
                req.upload.close()

    def _send(self, req: Request) -> Any:
        kwargs = self._build(req)
        try:
            response = self.client.request(**kwargs)
        except httpx.TimeoutException as error:
            raise APITimeoutError(f"Request timed out after {kwargs['timeout']} s") from error
        except httpx.TransportError as error:
            raise APIConnectionError("Could not connect to the Appress API") from error
        return handle_response(response)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()


class AsyncHTTP(_Base):
    def __init__(self, *, client: httpx.AsyncClient | None, **options: Any) -> None:
        super().__init__(**options)
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient()

    async def request(self, req: Request) -> Any:
        max_retries = self._max_retries(req)
        attempt = 0
        try:
            while True:
                try:
                    return await self._send(req)
                except (APIError, APIConnectionError) as error:
                    if attempt >= max_retries or not is_retryable(error):
                        raise
                    await async_sleep(retry_delay(error, attempt))
                    attempt += 1
        finally:
            if req.upload is not None:
                req.upload.close()

    async def _send(self, req: Request) -> Any:
        kwargs = self._build(req)
        try:
            response = await self.client.request(**kwargs)
        except httpx.TimeoutException as error:
            raise APITimeoutError(f"Request timed out after {kwargs['timeout']} s") from error
        except httpx.TransportError as error:
            raise APIConnectionError("Could not connect to the Appress API") from error
        return handle_response(response)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()


def handle_response(response: httpx.Response) -> Any:
    payload = _read_body(response)
    if not response.is_success:
        raise create_api_error(response.status_code, payload, response.headers)
    if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
        return payload["data"]
    return payload


def _read_body(response: httpx.Response) -> Any:
    text = response.text
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def _query_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def is_retryable(error: Exception) -> bool:
    if isinstance(error, APIConnectionError):
        return True
    return isinstance(error, APIError) and error.status in RETRYABLE_STATUS


def retry_delay(error: Exception, attempt: int) -> float:
    if isinstance(error, APIError):
        retry_after = parse_retry_after_seconds(error.headers.get("retry-after"))
        if retry_after is not None:
            return min(retry_after, MAX_RETRY_AFTER)
    base = min(INITIAL_RETRY_DELAY * 2.0**attempt, MAX_RETRY_DELAY)
    # ±25% jitter rather than full jitter: clients don't retry in lockstep, while
    # the wait stays predictable.
    return base * (0.75 + random.random() * 0.5)
