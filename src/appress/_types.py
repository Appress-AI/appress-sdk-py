"""Types for the Appress public API v1.

Source of truth: the published OpenAPI document (``GET /api-reference/openapi.json``).
Responses are plain ``dict`` objects at runtime, typed with ``TypedDict`` and keyed
exactly like the JSON (camelCase). Fields added by newer API versions simply
appear in the dict. ``scripts/check_contract.py`` reports drift.
"""

from __future__ import annotations

import os
import sys
from typing import IO, Any, Literal, TypedDict

from ._constants import (
    FeatureType,
    GenerationStatus,
    InputType,
    LiveTranscriptionPlatform,
    LiveTranscriptionState,
    NewsCategory,
    Tone,
)

if sys.version_info >= (3, 11):
    from typing import NotRequired
else:
    from typing_extensions import NotRequired

# ---------------------------------------------------------------------------
# feature_params
# ---------------------------------------------------------------------------


class TranscriptionParams(TypedDict, total=False):
    stt_lang: str
    """Source audio language. Defaults to ``tr``."""
    translate_lang: str
    """When set, the transcript is translated into this language."""
    title: str


class DiarizationParams(TypedDict, total=False):
    speakers_expected: int
    """Expected number of speakers (at least 1)."""
    title: str


class ProofreadingParams(TypedDict, total=False):
    language: Literal["tr", "intl"]
    """``tr`` (default) or ``intl`` for automatic language detection."""
    title: str


class NewsParams(TypedDict, total=False):
    mode: Literal["description"]
    news_lang: str
    tone: Tone
    news_category: NewsCategory
    speaker: str
    title: str
    date: str
    location: str
    topic: str
    notes: str


class PressReleaseParams(TypedDict, total=False):
    mode: Literal["description"]
    press_release_lang: str
    tone: Tone
    news_category: NewsCategory
    speaker: str
    title: str
    date: str
    location: str
    topic: str
    notes: str


class EventDetails(TypedDict):
    description: str
    news_category: NewsCategory
    tone: Tone
    language: str
    """Output language, e.g. ``tr``."""
    date: NotRequired[str]
    location: NotRequired[str]


class EventModeParams(TypedDict):
    """Event mode of NEWS and PRESS_RELEASE: no input, the event details are the source."""

    mode: Literal["event"]
    event: EventDetails


FeatureParams = (
    TranscriptionParams | DiarizationParams | ProofreadingParams | NewsParams | PressReleaseParams | EventModeParams
)

# ---------------------------------------------------------------------------
# File input
# ---------------------------------------------------------------------------

FileContent = bytes | IO[bytes]

FileInput = str | os.PathLike[str] | bytes | IO[bytes] | tuple[str, FileContent] | tuple[str, FileContent, str]
"""File to upload:

- a path (``str`` / ``pathlib.Path``): streamed from disk, not loaded into memory
- an open binary file (``open(path, "rb")``): sent whole; its ``name`` is the file name
- ``(file_name, bytes_or_file)`` or ``(file_name, bytes_or_file, content_type)``
"""

# ---------------------------------------------------------------------------
# Generations
# ---------------------------------------------------------------------------


class GenerationProgress(TypedDict):
    step: str | None
    percent: float | None


class TimedWord(TypedDict):
    """Word-level timing. ``s``/``e`` are seconds from the start of the source audio."""

    t: str
    s: float
    e: float


class DeltaOp(TypedDict, total=False):
    insert: str | dict[str, Any]
    retain: int
    delete: int
    attributes: dict[str, Any]


class DeltaDocument(TypedDict):
    ops: list[DeltaOp]


class GenerationResult(TypedDict):
    """A Quill Delta document. Line attributes depend on the feature; see the README."""

    ops: list[DeltaOp]
    diff: NotRequired[DeltaDocument]
    """PROOFREADING only: changes from the input to the corrected text, as delta ops."""


class TranscriptLineAttributes(TypedDict, total=False):
    """TRANSCRIPTION line attributes. Present only on lines aligned to the audio;
    never present when the transcript was translated (``translate_lang``)."""

    start: str
    """Line start, ``MM:SS`` or ``HH:MM:SS``."""
    end: str
    words: list[TimedWord]


class SpeakerTurnAttributes(TypedDict):
    """DIARIZATION (interview editor) attributes: one op per speaker turn."""

    speaker: str
    start: str
    end: str
    color: str
    words: NotRequired[list[TimedWord]]


class Generation(TypedDict):
    id: str
    featureType: FeatureType
    inputType: InputType
    status: GenerationStatus
    title: str | None
    progress: GenerationProgress
    estimatedCostUsd: str
    """Amount reserved at start, as a USD string with 6 decimals (e.g. ``"0.200000"``)."""
    actualCostUsd: str | None
    """Final settled amount; set only when ``COMPLETED``."""
    result: NotRequired[GenerationResult]
    """``COMPLETED`` only. Use ``get_result_text()`` for plain text."""
    quoteAnchors: NotRequired[Any]
    audioTimelineOffsetSeconds: NotRequired[float | None]
    originalText: NotRequired[str | None]
    error: NotRequired[str]
    """``ERROR`` / ``CANCELLED`` only: user-presentable error message."""
    createdAt: str
    updatedAt: str


class GenerationList(TypedDict):
    items: list[Generation]
    total: int


# ---------------------------------------------------------------------------
# Live transcription
# ---------------------------------------------------------------------------


class LiveTranscriptionWord(TypedDict):
    text: str
    startMs: int
    endMs: int
    confidence: float
    speaker: str | None


class LiveTranscriptionTurn(TypedDict):
    turnId: str
    sequence: int
    text: str
    isFinal: bool
    startMs: int | None
    endMs: int | None
    speaker: str | None
    language: str | None
    words: list[LiveTranscriptionWord] | None
    """Set only when the session was started with ``include_words=True``."""


class LiveTranscription(TypedDict):
    id: str
    url: str | None
    generationId: str
    state: LiveTranscriptionState
    platform: LiveTranscriptionPlatform
    expectedLanguage: str
    maxDurationMinutes: int
    expiresAt: str | None
    lastSequence: int
    mediaTitle: str | None
    failureCode: str | None
    failureMessage: str | None
    turns: list[LiveTranscriptionTurn]
    createdAt: str
    startedAt: str | None
    completedAt: str | None
    reservedCostUsd: str


class ActiveLiveTranscription(TypedDict):
    id: str
    url: str | None
    generationId: str
    title: str | None
    state: LiveTranscriptionState
    platform: LiveTranscriptionPlatform
    maxDurationMinutes: int
    expiresAt: str | None
    startedAt: str | None
    createdAt: str
    reservedCostUsd: str


class LiveDurationOption(TypedDict):
    minutes: int
    reservedCostUsd: str


class LiveTranscriptionOptions(TypedDict):
    durationOptions: list[LiveDurationOption]


class LiveExtendOption(TypedDict):
    totalDurationMinutes: int
    additionalReservedCostUsd: str
    totalReservedCostUsd: str


class LiveTranscriptionExtendOptions(TypedDict):
    currentDurationMinutes: int
    currentReservedCostUsd: str
    options: list[LiveExtendOption]
