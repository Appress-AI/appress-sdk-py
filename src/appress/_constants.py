"""Enum values of the API contract.

Each ``Literal`` type is the single source; the tuples are derived from it and
``scripts/check_contract.py`` compares them with the published OpenAPI document.
"""

from __future__ import annotations

from typing import Literal, get_args

FeatureType = Literal[
    "TRANSCRIPTION",
    "LIVE_TRANSCRIPTION",
    "PRESS_RELEASE",
    "NEWS",
    "DIARIZATION",
    "PROOFREADING",
]
FEATURE_TYPES: tuple[FeatureType, ...] = get_args(FeatureType)

#: Features that can be started through ``/v1/generations`` (everything except live transcription).
GenerationFeatureType = Literal["TRANSCRIPTION", "PRESS_RELEASE", "NEWS", "DIARIZATION", "PROOFREADING"]

GenerationStatus = Literal["PENDING", "PROCESSING", "COMPLETED", "ERROR", "CANCELLED"]
GENERATION_STATUSES: tuple[GenerationStatus, ...] = get_args(GenerationStatus)

InputType = Literal["TEXT", "URL", "FILE"]
INPUT_TYPES: tuple[InputType, ...] = get_args(InputType)

LiveTranscriptionState = Literal[
    "CREATED",
    "RESOLVING_SOURCE",
    "CONNECTING_STT",
    "STREAMING",
    "STOPPING",
    "COMPLETED",
    "FAILED",
]
LIVE_TRANSCRIPTION_STATES: tuple[LiveTranscriptionState, ...] = get_args(LiveTranscriptionState)

LiveTranscriptionPlatform = Literal["youtube", "x", "microphone"]
LIVE_TRANSCRIPTION_PLATFORMS: tuple[LiveTranscriptionPlatform, ...] = get_args(LiveTranscriptionPlatform)

#: ``news_category`` values for NEWS and PRESS_RELEASE.
NewsCategory = Literal[
    "politics",
    "economy_finance_energy",
    "sports",
    "technology",
    "health",
    "education",
    "culture_arts",
    "diplomacy",
    "defense",
    "police_justice",
    "terrorism",
    "traffic_accident",
    "mining_accident",
    "natural_disaster",
    "environment_agriculture",
]
NEWS_CATEGORIES: tuple[NewsCategory, ...] = get_args(NewsCategory)

Tone = Literal["Objective", "Critical", "Investigative", "Marketing", "Supportive"]
TONES: tuple[Tone, ...] = get_args(Tone)

#: Stable error codes the API can return under ``/v1``.
ErrorCode = Literal[
    "IDEMPOTENCY_KEY_REQUIRED",
    "IDEMPOTENCY_KEY_CONFLICT",
    "IDEMPOTENCY_REQUEST_IN_PROGRESS",
    "CONCURRENT_GENERATION_LIMIT",
    "LIVE_SESSION_NOT_EXTENDABLE",
    "LIVE_EXTENSION_IN_PROGRESS",
    "LIVE_EXTENSION_INVALID",
    "INSUFFICIENT_API_CREDIT",
    "INVALID_API_KEY",
    "RATE_LIMIT_EXCEEDED",
    "RATE_LIMIT_UNAVAILABLE",
    "DB_POOL_SATURATED",
]
ERROR_CODES: tuple[ErrorCode, ...] = get_args(ErrorCode)

#: A generation in one of these statuses never changes again.
TERMINAL_GENERATION_STATUSES: tuple[GenerationStatus, ...] = ("COMPLETED", "ERROR", "CANCELLED")

#: A live session in one of these states never changes again.
TERMINAL_LIVE_STATES: tuple[LiveTranscriptionState, ...] = ("COMPLETED", "FAILED")
