from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from typing import Any, cast
from urllib.parse import quote

from .. import _http
from .._constants import TERMINAL_LIVE_STATES
from .._http import AsyncHTTP, Request, SyncHTTP
from .._types import (
    ActiveLiveTranscription,
    LiveTranscription,
    LiveTranscriptionExtendOptions,
    LiveTranscriptionOptions,
    LiveTranscriptionTurn,
)

#: Python argument → JSON field of ``POST /v1/live-transcriptions``.
CREATE_FIELDS = {
    "url": "url",
    "title": "title",
    "expected_language": "expectedLanguage",
    "speaker_labels": "speakerLabels",
    "max_speakers": "maxSpeakers",
    "include_words": "includeWords",
    "max_duration_minutes": "maxDurationMinutes",
}

#: Python argument → JSON field of ``POST /v1/live-transcriptions/{id}/extend``.
EXTEND_FIELDS = {"total_duration_minutes": "totalDurationMinutes"}

DEFAULT_POLL_INTERVAL = 2.0

_BASE = "/v1/live-transcriptions"


def _path(id: str, suffix: str = "") -> str:
    return f"{_BASE}/{quote(id, safe='')}{suffix}"


def _request(
    method: str,
    path: str,
    *,
    timeout: float | None,
    max_retries: int | None,
    extra_headers: Mapping[str, str] | None,
    json: Any = None,
    idempotency_key: str | None = None,
) -> Request:
    return Request(
        method=method,
        path=path,
        json=json,
        idempotency_key=idempotency_key,
        timeout=timeout,
        max_retries=max_retries,
        headers=extra_headers or {},
    )


def _create_body(values: Mapping[str, Any]) -> dict[str, Any]:
    return {CREATE_FIELDS[key]: value for key, value in values.items() if value is not None}


class _TurnFilter:
    """Remembers what was yielded: final turns once, interim turns when their text changes."""

    def __init__(self, include_partial: bool) -> None:
        self.include_partial = include_partial
        # turnId -> (last yielded text, is final)
        self.emitted: dict[str, tuple[str, bool]] = {}

    def new_turns(self, session: LiveTranscription) -> list[LiveTranscriptionTurn]:
        turns = []
        for turn in session["turns"]:
            previous = self.emitted.get(turn["turnId"])
            if previous is not None and previous[1]:
                continue
            if not turn["isFinal"] and (
                not self.include_partial or (previous is not None and previous[0] == turn["text"])
            ):
                continue
            self.emitted[turn["turnId"]] = (turn["text"], turn["isFinal"])
            turns.append(turn)
        return turns


class LiveTranscriptions:
    """``client.live_transcriptions``: live stream transcription sessions."""

    def __init__(self, http: SyncHTTP) -> None:
        self._http = http

    def options(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscriptionOptions:
        """Available durations and the amount reserved for each."""
        request = _request(
            "GET", f"{_BASE}/options", timeout=timeout, max_retries=max_retries, extra_headers=extra_headers
        )
        return cast(LiveTranscriptionOptions, self._http.request(request))

    def active(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> list[ActiveLiveTranscription]:
        """Active sessions of this API key."""
        request = _request(
            "GET", f"{_BASE}/active", timeout=timeout, max_retries=max_retries, extra_headers=extra_headers
        )
        return cast("list[ActiveLiveTranscription]", self._http.request(request))

    def create(
        self,
        *,
        url: str,
        title: str | None = None,
        expected_language: str | None = None,
        speaker_labels: bool | None = None,
        max_speakers: int | None = None,
        include_words: bool | None = None,
        max_duration_minutes: int | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscription:
        """Starts a live transcription (``202 Accepted``). The amount for the chosen duration is reserved.

        ``max_duration_minutes`` is one of the durations from :meth:`options` (default 120).
        ``max_speakers`` (1-10) only together with ``speaker_labels=True``.
        """
        body = _create_body(
            {
                "url": url,
                "title": title,
                "expected_language": expected_language,
                "speaker_labels": speaker_labels,
                "max_speakers": max_speakers,
                "include_words": include_words,
                "max_duration_minutes": max_duration_minutes,
            }
        )
        request = _request(
            "POST",
            _BASE,
            json=body,
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )
        return cast(LiveTranscription, self._http.request(request))

    def retrieve(
        self,
        id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscription:
        """Returns the session with all turns so far."""
        request = _request("GET", _path(id), timeout=timeout, max_retries=max_retries, extra_headers=extra_headers)
        return cast(LiveTranscription, self._http.request(request))

    def stop(
        self,
        id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscription:
        """Stops an active session. For a session that already ended, returns it unchanged."""
        request = _request(
            "POST", _path(id, "/stop"), timeout=timeout, max_retries=max_retries, extra_headers=extra_headers
        )
        return cast(LiveTranscription, self._http.request(request))

    def extend_options(
        self,
        id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscriptionExtendOptions:
        """Total durations the session can be extended to, with the additional reservation for each."""
        request = _request(
            "GET", _path(id, "/extend-options"), timeout=timeout, max_retries=max_retries, extra_headers=extra_headers
        )
        return cast(LiveTranscriptionExtendOptions, self._http.request(request))

    def extend(
        self,
        id: str,
        *,
        total_duration_minutes: int,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscription:
        """Extends the session's total duration; the difference is reserved additionally."""
        request = _request(
            "POST",
            _path(id, "/extend"),
            json={EXTEND_FIELDS["total_duration_minutes"]: total_duration_minutes},
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )
        return cast(LiveTranscription, self._http.request(request))

    def stream_turns(
        self,
        id: str,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        include_partial: bool = False,
        on_session: Callable[[LiveTranscription], object] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Iterator[LiveTranscriptionTurn]:
        """Polls the session and yields new turns in order; ends when it is ``COMPLETED`` or ``FAILED``.

        With ``include_partial=True`` interim turns are also yielded whenever their
        text changes. Breaking out of the loop does NOT stop the session: call
        :meth:`stop` for that.
        """
        turns = _TurnFilter(include_partial)
        while True:
            session = self.retrieve(id, timeout=timeout, max_retries=max_retries, extra_headers=extra_headers)
            if on_session is not None:
                on_session(session)
            yield from turns.new_turns(session)
            if session["state"] in TERMINAL_LIVE_STATES:
                return
            _http.sleep(poll_interval)


class AsyncLiveTranscriptions:
    """``client.live_transcriptions`` of :class:`AsyncAppress`."""

    def __init__(self, http: AsyncHTTP) -> None:
        self._http = http

    async def options(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscriptionOptions:
        """See :meth:`LiveTranscriptions.options`."""
        request = _request(
            "GET", f"{_BASE}/options", timeout=timeout, max_retries=max_retries, extra_headers=extra_headers
        )
        return cast(LiveTranscriptionOptions, await self._http.request(request))

    async def active(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> list[ActiveLiveTranscription]:
        """See :meth:`LiveTranscriptions.active`."""
        request = _request(
            "GET", f"{_BASE}/active", timeout=timeout, max_retries=max_retries, extra_headers=extra_headers
        )
        return cast("list[ActiveLiveTranscription]", await self._http.request(request))

    async def create(
        self,
        *,
        url: str,
        title: str | None = None,
        expected_language: str | None = None,
        speaker_labels: bool | None = None,
        max_speakers: int | None = None,
        include_words: bool | None = None,
        max_duration_minutes: int | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscription:
        """See :meth:`LiveTranscriptions.create`."""
        body = _create_body(
            {
                "url": url,
                "title": title,
                "expected_language": expected_language,
                "speaker_labels": speaker_labels,
                "max_speakers": max_speakers,
                "include_words": include_words,
                "max_duration_minutes": max_duration_minutes,
            }
        )
        request = _request(
            "POST",
            _BASE,
            json=body,
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )
        return cast(LiveTranscription, await self._http.request(request))

    async def retrieve(
        self,
        id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscription:
        """See :meth:`LiveTranscriptions.retrieve`."""
        request = _request("GET", _path(id), timeout=timeout, max_retries=max_retries, extra_headers=extra_headers)
        return cast(LiveTranscription, await self._http.request(request))

    async def stop(
        self,
        id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscription:
        """See :meth:`LiveTranscriptions.stop`."""
        request = _request(
            "POST", _path(id, "/stop"), timeout=timeout, max_retries=max_retries, extra_headers=extra_headers
        )
        return cast(LiveTranscription, await self._http.request(request))

    async def extend_options(
        self,
        id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscriptionExtendOptions:
        """See :meth:`LiveTranscriptions.extend_options`."""
        request = _request(
            "GET", _path(id, "/extend-options"), timeout=timeout, max_retries=max_retries, extra_headers=extra_headers
        )
        return cast(LiveTranscriptionExtendOptions, await self._http.request(request))

    async def extend(
        self,
        id: str,
        *,
        total_duration_minutes: int,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LiveTranscription:
        """See :meth:`LiveTranscriptions.extend`."""
        request = _request(
            "POST",
            _path(id, "/extend"),
            json={EXTEND_FIELDS["total_duration_minutes"]: total_duration_minutes},
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )
        return cast(LiveTranscription, await self._http.request(request))

    async def stream_turns(
        self,
        id: str,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        include_partial: bool = False,
        on_session: Callable[[LiveTranscription], object | Awaitable[object]] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[LiveTranscriptionTurn]:
        """See :meth:`LiveTranscriptions.stream_turns`. ``on_session`` may be async."""
        turns = _TurnFilter(include_partial)
        while True:
            session = await self.retrieve(id, timeout=timeout, max_retries=max_retries, extra_headers=extra_headers)
            if on_session is not None:
                outcome = on_session(session)
                if inspect.isawaitable(outcome):
                    await outcome
            for turn in turns.new_turns(session):
                yield turn
            if session["state"] in TERMINAL_LIVE_STATES:
                return
            await _http.async_sleep(poll_interval)
