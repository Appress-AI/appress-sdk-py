"""Compares the SDK's contract assumptions with the published OpenAPI document.

    python scripts/check_contract.py                       # live https://api.appress.ai document
    python scripts/check_contract.py ./path/to/openapi.json  # a local or unreleased document

Lists added/removed endpoints, enum values or fields and exits with 1. A
difference means ``_types.py`` / ``_constants.py`` and the resources need an update.
Response fields are read from the ``TypedDict`` types and request fields from the
resources' field maps, so this file only names which schema maps to which type.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin

import httpx

import appress
from appress.resources import generations, live_transcriptions

DEFAULT_SOURCE = "https://api.appress.ai/api-reference/openapi.json"

#: Endpoints wrapped by the SDK (method + OpenAPI path).
ENDPOINTS = [
    "POST /v1/generations",
    "GET /v1/generations",
    "GET /v1/generations/{id}",
    "GET /v1/live-transcriptions/options",
    "GET /v1/live-transcriptions/active",
    "POST /v1/live-transcriptions",
    "GET /v1/live-transcriptions/{id}",
    "GET /v1/live-transcriptions/{id}/extend-options",
    "POST /v1/live-transcriptions/{id}/stop",
    "POST /v1/live-transcriptions/{id}/extend",
]

#: Endpoints that receive an ``Idempotency-Key``.
IDEMPOTENT = ["POST /v1/generations", "POST /v1/live-transcriptions", "POST /v1/live-transcriptions/{id}/extend"]

#: OpenAPI enum schema -> SDK constant.
ENUMS: dict[str, Iterable[str]] = {
    "FeatureType": appress.FEATURE_TYPES,
    "GenerationStatus": appress.GENERATION_STATUSES,
    "ApiGenerationInputType": appress.INPUT_TYPES,
    "LiveTranscriptionState": appress.LIVE_TRANSCRIPTION_STATES,
    "LiveTranscriptionPlatform": appress.LIVE_TRANSCRIPTION_PLATFORMS,
    "LiveTranscriptionFailureCode": appress.LIVE_TRANSCRIPTION_FAILURE_CODES,
    "GenerationProgressStep": appress.GENERATION_PROGRESS_STEPS,
}


def typed_dict_fields(cls: Any) -> list[str]:
    return sorted(cls.__required_keys__ | cls.__optional_keys__)


#: OpenAPI object schema -> fields the SDK knows.
OBJECTS: dict[str, list[str]] = {
    "ApiGenerationDto": typed_dict_fields(appress.Generation),
    "ApiGenerationProgressDto": typed_dict_fields(appress.GenerationProgress),
    "ApiGenerationListDto": typed_dict_fields(appress.GenerationList),
    "ApiLiveSessionDto": typed_dict_fields(appress.LiveTranscription),
    "ApiLiveTurnDto": typed_dict_fields(appress.LiveTranscriptionTurn),
    "ApiLiveWordDto": typed_dict_fields(appress.LiveTranscriptionWord),
    "ApiActiveLiveSessionDto": typed_dict_fields(appress.ActiveLiveTranscription),
    "ApiLiveOptionsDto": typed_dict_fields(appress.LiveTranscriptionOptions),
    "ApiLiveDurationOptionDto": typed_dict_fields(appress.LiveDurationOption),
    "ApiLiveExtendOptionsDto": typed_dict_fields(appress.LiveTranscriptionExtendOptions),
    "ApiLiveExtendOptionDto": typed_dict_fields(appress.LiveExtendOption),
    "CreateApiGenerationDto": list(generations.CREATE_FIELDS.values()),
    # `source` is intentionally not exposed: the API only accepts its default.
    "CreateLiveTranscriptionDto": [*live_transcriptions.CREATE_FIELDS.values(), "source"],
    "ExtendApiLiveTranscriptionDto": list(live_transcriptions.EXTEND_FIELDS.values()),
}


def load(source: str) -> Any:
    if source.startswith(("http://", "https://")):
        response = httpx.get(source, timeout=30)
        response.raise_for_status()
        return response.json()
    with open(source, encoding="utf-8") as file:
        return json.load(file)


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE
    spec = load(source)
    problems: list[str] = []

    def diff(label: str, expected: Iterable[str], actual: Iterable[str]) -> None:
        expected, actual = list(expected), list(actual)
        missing = [v for v in actual if v not in expected]
        extra = [v for v in expected if v not in actual]
        if missing:
            problems.append(f"{label}: in API, missing in SDK -> {', '.join(missing)}")
        if extra:
            problems.append(f"{label}: in SDK, missing in API -> {', '.join(extra)}")

    operations = [
        (f"{method.upper()} {path}", operation)
        for path, methods in (spec.get("paths") or {}).items()
        for method, operation in methods.items()
    ]
    diff("Endpoints", ENDPOINTS, [key for key, _ in operations])

    for key, operation in operations:
        has_key = any(
            p.get("in") == "header" and p.get("name", "").lower() == "idempotency-key"
            for p in operation.get("parameters") or []
        )
        if has_key != (key in IDEMPOTENT):
            state = "required by API, not sent by SDK" if has_key else "sent by SDK, not declared by API"
            problems.append(f"{key}: Idempotency-Key {state}")

    schemas = (spec.get("components") or {}).get("schemas") or {}
    for name, values in ENUMS.items():
        if "enum" not in schemas.get(name, {}):
            problems.append(f"Missing enum schema: {name}")
        else:
            diff(f"Enum {name}", values, schemas[name]["enum"])
    for name, fields in OBJECTS.items():
        if "properties" not in schemas.get(name, {}):
            problems.append(f"Missing object schema: {name}")
        else:
            diff(f"Fields {name}", fields, schemas[name]["properties"].keys())

    # Values published only in `GET /api-reference/config` (not in the OpenAPI document).
    if source.startswith(("http://", "https://")):
        config_url: str | None = urljoin(source, "/api-reference/config")
    else:
        config_url = os.environ.get("APPRESS_CONFIG_URL")
    if config_url:
        config = load(config_url).get("data") or {}
        diff("News categories", appress.NEWS_CATEGORIES, (config.get("generations") or {}).get("newsCategories") or [])
        live = config.get("liveTranscription") or {}
        diff("Live failure codes", appress.LIVE_TRANSCRIPTION_FAILURE_CODES, live.get("failureCodes") or [])
        codes = [entry.get("code") for entry in (config.get("errors") or {}).get("codes") or []]
        diff("Error codes", appress.ERROR_CODES, codes)

    if problems:
        print(f"Contract drift ({source}):\n- " + "\n- ".join(problems), file=sys.stderr)
        return 1
    print(f"SDK contract is up to date ({len(operations)} endpoints, {len(ENUMS)} enums, {len(OBJECTS)} schemas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
