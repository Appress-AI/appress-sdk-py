from __future__ import annotations

import os
from collections.abc import Mapping
from types import TracebackType
from typing import Any

import httpx

from ._errors import AppressError
from ._http import DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, AsyncHTTP, Request, SyncHTTP
from .resources.generations import AsyncGenerations, Generations
from .resources.live_transcriptions import AsyncLiveTranscriptions, LiveTranscriptions


def _options(
    api_key: str | None,
    base_url: str | None,
    timeout: float,
    max_retries: int,
    default_headers: Mapping[str, str] | None,
) -> dict[str, Any]:
    key = api_key or os.environ.get("APPRESS_API_KEY")
    if not key:
        raise AppressError("Missing API key: pass Appress(api_key=...) or set the APPRESS_API_KEY environment variable")
    return {
        "api_key": key,
        "base_url": base_url or os.environ.get("APPRESS_BASE_URL") or DEFAULT_BASE_URL,
        "timeout": timeout,
        "max_retries": max_retries,
        "default_headers": default_headers or {},
    }


def _raw_request(
    method: str,
    path: str,
    query: Mapping[str, Any] | None,
    body: Any,
    timeout: float | None,
    max_retries: int | None,
    extra_headers: Mapping[str, str] | None,
) -> Request:
    return Request(
        method=method.upper(),
        path=path,
        query=query,
        json=body,
        timeout=timeout,
        max_retries=max_retries,
        headers=extra_headers or {},
    )


class Appress:
    """Client for the Appress public API.

    :param api_key: Defaults to the ``APPRESS_API_KEY`` environment variable.
    :param base_url: Defaults to ``APPRESS_BASE_URL`` or ``https://api.appress.ai``.
    :param timeout: Per-request timeout in seconds (60). File uploads default to 30 minutes.
    :param max_retries: Retries on 408/429/502/503/504 and network errors (4).
    :param default_headers: Headers added to every request.
    :param http_client: A custom ``httpx.Client`` (proxy, transport). Not closed by :meth:`close`.
    """

    generations: Generations
    live_transcriptions: LiveTranscriptions

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._http = SyncHTTP(client=http_client, **_options(api_key, base_url, timeout, max_retries, default_headers))
        self.generations = Generations(self._http)
        self.live_transcriptions = LiveTranscriptions(self._http)

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Any = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Raw request for an endpoint without a typed helper.

        The ``{success, data}`` envelope is unwrapped; errors and retries behave like
        the other methods.
        """
        return self._http.request(_raw_request(method, path, query, body, timeout, max_retries, extra_headers))

    def close(self) -> None:
        """Closes the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> Appress:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.close()


class AsyncAppress:
    """``asyncio`` client for the Appress public API. Same options as :class:`Appress`."""

    generations: AsyncGenerations
    live_transcriptions: AsyncLiveTranscriptions

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._http = AsyncHTTP(client=http_client, **_options(api_key, base_url, timeout, max_retries, default_headers))
        self.generations = AsyncGenerations(self._http)
        self.live_transcriptions = AsyncLiveTranscriptions(self._http)

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Any = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Any:
        """See :meth:`Appress.request`."""
        return await self._http.request(_raw_request(method, path, query, body, timeout, max_retries, extra_headers))

    async def close(self) -> None:
        """Closes the underlying HTTP connection pool."""
        await self._http.close()

    async def __aenter__(self) -> AsyncAppress:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.close()
