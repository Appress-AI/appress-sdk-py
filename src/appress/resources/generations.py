from __future__ import annotations

import inspect
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from typing import Any, cast
from urllib.parse import quote

from .. import _http
from .._constants import TERMINAL_GENERATION_STATUSES, FeatureType, GenerationFeatureType, GenerationStatus
from .._errors import WaitTimeoutError
from .._files import Upload
from .._http import UPLOAD_TIMEOUT, AsyncHTTP, Request, SyncHTTP
from .._types import FeatureParams, FileInput, Generation, GenerationList

#: Python argument → JSON field of ``POST /v1/generations`` (``file`` is the multipart part).
CREATE_FIELDS = {
    "feature_type": "featureType",
    "input_text": "inputText",
    "input_url": "inputUrl",
    "feature_params": "featureParams",
}

#: Python argument → query parameter of ``GET /v1/generations``.
LIST_FIELDS = {
    "skip": "skip",
    "take": "take",
    "feature_type": "featureType",
    "status": "status",
    "api_key_id": "apiKeyId",
}

DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_MAX_POLL_INTERVAL = 10.0
DEFAULT_WAIT_TIMEOUT = 30 * 60.0


def _create_request(
    *,
    feature_type: str,
    input_text: str | None,
    input_url: str | None,
    file: FileInput | None,
    feature_params: Mapping[str, Any] | None,
    idempotency_key: str | None,
    timeout: float | None,
    max_retries: int | None,
    extra_headers: Mapping[str, str] | None,
) -> Request:
    inputs = sum(value is not None for value in (input_text, input_url, file))
    event_mode = feature_params is not None and feature_params.get("mode") == "event"
    if event_mode and inputs:
        raise ValueError("Event mode takes no input: omit input_text, input_url and file")
    if not event_mode and inputs != 1:
        raise ValueError("Pass exactly one of input_text, input_url or file")

    values = {"feature_type": feature_type, "input_text": input_text, "input_url": input_url}
    body: dict[str, Any] = {CREATE_FIELDS[key]: value for key, value in values.items() if value is not None}
    if feature_params is not None:
        body["featureParams"] = dict(feature_params)

    request = Request(
        method="POST",
        path="/v1/generations",
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        timeout=timeout,
        max_retries=max_retries,
        headers=extra_headers or {},
    )
    if file is None:
        request.json = body
    else:
        # In multipart bodies featureParams is sent as a JSON string.
        request.form = {
            key: json.dumps(value) if isinstance(value, dict) else str(value) for key, value in body.items()
        }
        request.upload = Upload(file)
        if timeout is None:
            request.timeout = UPLOAD_TIMEOUT
    return request


def _list_query(
    skip: int | None, take: int | None, feature_type: str | None, status: str | None, api_key_id: str | None
) -> dict[str, Any]:
    values = {"skip": skip, "take": take, "feature_type": feature_type, "status": status, "api_key_id": api_key_id}
    return {LIST_FIELDS[key]: value for key, value in values.items() if value is not None}


def _retrieve_request(
    id: str, timeout: float | None, max_retries: int | None, extra_headers: Mapping[str, str] | None
) -> Request:
    return Request(
        method="GET",
        path=f"/v1/generations/{_quote(id)}",
        timeout=timeout,
        max_retries=max_retries,
        headers=extra_headers or {},
    )


def _quote(id: str) -> str:
    return quote(id, safe="")


class Generations:
    """``client.generations``: asynchronous generation jobs."""

    def __init__(self, http: SyncHTTP) -> None:
        self._http = http

    def create(
        self,
        *,
        feature_type: GenerationFeatureType,
        input_text: str | None = None,
        input_url: str | None = None,
        file: FileInput | None = None,
        feature_params: FeatureParams | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Generation:
        """Starts an asynchronous generation (``202 Accepted``).

        Use :meth:`retrieve` or :meth:`wait_for_completion` for the result. Send exactly
        one of ``input_text``, ``input_url`` or ``file``, except in event mode. An
        ``Idempotency-Key`` is generated automatically and kept across retries.
        """
        request = _create_request(
            feature_type=feature_type,
            input_text=input_text,
            input_url=input_url,
            file=file,
            feature_params=cast("Mapping[str, Any] | None", feature_params),
            idempotency_key=idempotency_key,
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )
        return cast(Generation, self._http.request(request))

    def retrieve(
        self,
        id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Generation:
        """Returns the current status of a generation, and its result once completed."""
        return cast(Generation, self._http.request(_retrieve_request(id, timeout, max_retries, extra_headers)))

    def list(
        self,
        *,
        skip: int | None = None,
        take: int | None = None,
        feature_type: FeatureType | None = None,
        status: GenerationStatus | None = None,
        api_key_id: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> GenerationList:
        """Lists your account's API generations, paginated (``{"items", "total"}``).

        ``take`` is 1-100 (default 20). ``api_key_id`` limits the list to one API key.
        """
        request = Request(
            method="GET",
            path="/v1/generations",
            query=_list_query(skip, take, feature_type, status, api_key_id),
            timeout=timeout,
            max_retries=max_retries,
            headers=extra_headers or {},
        )
        return cast(GenerationList, self._http.request(request))

    def iterate(
        self,
        *,
        take: int = 100,
        feature_type: FeatureType | None = None,
        status: GenerationStatus | None = None,
        api_key_id: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Iterator[Generation]:
        """Walks every page in order: ``for g in client.generations.iterate(): ...``."""
        skip = 0
        while True:
            page = self.list(
                skip=skip,
                take=take,
                feature_type=feature_type,
                status=status,
                api_key_id=api_key_id,
                timeout=timeout,
                max_retries=max_retries,
                extra_headers=extra_headers,
            )
            yield from page["items"]
            if len(page["items"]) < take or skip + len(page["items"]) >= page["total"]:
                return
            skip += take

    def wait_for_completion(
        self,
        id: str,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_poll_interval: float = DEFAULT_MAX_POLL_INTERVAL,
        wait_timeout: float | None = DEFAULT_WAIT_TIMEOUT,
        on_progress: Callable[[Generation], object] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Generation:
        """Polls until the generation is ``COMPLETED``, ``ERROR`` or ``CANCELLED`` and returns it.

        ``ERROR``/``CANCELLED`` do not raise: check ``status`` and ``error``. Polling
        starts at ``poll_interval`` seconds and backs off to ``max_poll_interval``.
        Raises :class:`WaitTimeoutError` after ``wait_timeout`` seconds (``None`` for
        no limit); the job may still be running and can be awaited again.
        """
        deadline = None if wait_timeout is None else time.monotonic() + wait_timeout
        interval = poll_interval
        while True:
            generation = self.retrieve(id, timeout=timeout, max_retries=max_retries, extra_headers=extra_headers)
            if on_progress is not None:
                on_progress(generation)
            if generation["status"] in TERMINAL_GENERATION_STATUSES:
                return generation
            delay = _next_delay(deadline, interval, wait_timeout, id, generation)
            _http.sleep(delay)
            # Long jobs are polled less often over time: 2 -> 3 -> 4.5 -> ... -> 10 s.
            interval = min(interval * 1.5, max_poll_interval)

    def create_and_wait(
        self,
        *,
        feature_type: GenerationFeatureType,
        input_text: str | None = None,
        input_url: str | None = None,
        file: FileInput | None = None,
        feature_params: FeatureParams | None = None,
        idempotency_key: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_poll_interval: float = DEFAULT_MAX_POLL_INTERVAL,
        wait_timeout: float | None = DEFAULT_WAIT_TIMEOUT,
        on_progress: Callable[[Generation], object] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Generation:
        """Shortcut for :meth:`create` followed by :meth:`wait_for_completion`."""
        created = self.create(
            feature_type=feature_type,
            input_text=input_text,
            input_url=input_url,
            file=file,
            feature_params=feature_params,
            idempotency_key=idempotency_key,
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )
        return self.wait_for_completion(
            created["id"],
            poll_interval=poll_interval,
            max_poll_interval=max_poll_interval,
            wait_timeout=wait_timeout,
            on_progress=on_progress,
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )


class AsyncGenerations:
    """``client.generations`` of :class:`AsyncAppress`."""

    def __init__(self, http: AsyncHTTP) -> None:
        self._http = http

    async def create(
        self,
        *,
        feature_type: GenerationFeatureType,
        input_text: str | None = None,
        input_url: str | None = None,
        file: FileInput | None = None,
        feature_params: FeatureParams | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Generation:
        """See :meth:`Generations.create`."""
        request = _create_request(
            feature_type=feature_type,
            input_text=input_text,
            input_url=input_url,
            file=file,
            feature_params=cast("Mapping[str, Any] | None", feature_params),
            idempotency_key=idempotency_key,
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )
        return cast(Generation, await self._http.request(request))

    async def retrieve(
        self,
        id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Generation:
        """See :meth:`Generations.retrieve`."""
        return cast(Generation, await self._http.request(_retrieve_request(id, timeout, max_retries, extra_headers)))

    async def list(
        self,
        *,
        skip: int | None = None,
        take: int | None = None,
        feature_type: FeatureType | None = None,
        status: GenerationStatus | None = None,
        api_key_id: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> GenerationList:
        """See :meth:`Generations.list`."""
        request = Request(
            method="GET",
            path="/v1/generations",
            query=_list_query(skip, take, feature_type, status, api_key_id),
            timeout=timeout,
            max_retries=max_retries,
            headers=extra_headers or {},
        )
        return cast(GenerationList, await self._http.request(request))

    async def iterate(
        self,
        *,
        take: int = 100,
        feature_type: FeatureType | None = None,
        status: GenerationStatus | None = None,
        api_key_id: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[Generation]:
        """Walks every page in order: ``async for g in client.generations.iterate(): ...``."""
        skip = 0
        while True:
            page = await self.list(
                skip=skip,
                take=take,
                feature_type=feature_type,
                status=status,
                api_key_id=api_key_id,
                timeout=timeout,
                max_retries=max_retries,
                extra_headers=extra_headers,
            )
            for item in page["items"]:
                yield item
            if len(page["items"]) < take or skip + len(page["items"]) >= page["total"]:
                return
            skip += take

    async def wait_for_completion(
        self,
        id: str,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_poll_interval: float = DEFAULT_MAX_POLL_INTERVAL,
        wait_timeout: float | None = DEFAULT_WAIT_TIMEOUT,
        on_progress: Callable[[Generation], object | Awaitable[object]] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Generation:
        """See :meth:`Generations.wait_for_completion`. ``on_progress`` may be async."""
        deadline = None if wait_timeout is None else time.monotonic() + wait_timeout
        interval = poll_interval
        while True:
            generation = await self.retrieve(id, timeout=timeout, max_retries=max_retries, extra_headers=extra_headers)
            if on_progress is not None:
                outcome = on_progress(generation)
                if inspect.isawaitable(outcome):
                    await outcome
            if generation["status"] in TERMINAL_GENERATION_STATUSES:
                return generation
            await _http.async_sleep(_next_delay(deadline, interval, wait_timeout, id, generation))
            interval = min(interval * 1.5, max_poll_interval)

    async def create_and_wait(
        self,
        *,
        feature_type: GenerationFeatureType,
        input_text: str | None = None,
        input_url: str | None = None,
        file: FileInput | None = None,
        feature_params: FeatureParams | None = None,
        idempotency_key: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_poll_interval: float = DEFAULT_MAX_POLL_INTERVAL,
        wait_timeout: float | None = DEFAULT_WAIT_TIMEOUT,
        on_progress: Callable[[Generation], object | Awaitable[object]] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Generation:
        """See :meth:`Generations.create_and_wait`."""
        created = await self.create(
            feature_type=feature_type,
            input_text=input_text,
            input_url=input_url,
            file=file,
            feature_params=feature_params,
            idempotency_key=idempotency_key,
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )
        return await self.wait_for_completion(
            created["id"],
            poll_interval=poll_interval,
            max_poll_interval=max_poll_interval,
            wait_timeout=wait_timeout,
            on_progress=on_progress,
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )


def _next_delay(
    deadline: float | None, interval: float, wait_timeout: float | None, id: str, generation: Generation
) -> float:
    if deadline is None:
        return interval
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WaitTimeoutError(
            f"Generation did not finish within {wait_timeout} s (last status: {generation['status']})", id
        )
    return min(interval, remaining)
