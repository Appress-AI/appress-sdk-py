"""Webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from collections.abc import Iterable, Mapping
from typing import Any, cast

from ._errors import AppressError
from ._types import WebhookEvent

WEBHOOK_ID_HEADER = "appress-webhook-id"
WEBHOOK_TIMESTAMP_HEADER = "appress-webhook-timestamp"
WEBHOOK_SIGNATURE_HEADER = "appress-webhook-signature"
#: Default maximum age of a delivery, in seconds.
DEFAULT_WEBHOOK_TOLERANCE_SECONDS = 300

_SEPARATOR = re.compile(r"[\s,]+")


class WebhookVerificationError(AppressError):
    """The delivery could not be verified; respond with a non-2xx status and do not process it."""


def _header(headers: Mapping[str, Any] | Iterable[tuple[str, str]], name: str) -> str | None:
    items = headers.items() if isinstance(headers, Mapping) else headers
    for key, value in items:
        if str(key).lower() != name:
            continue
        if isinstance(value, (list, tuple)):
            return " ".join(str(v) for v in value)
        if isinstance(value, bytes):
            return value.decode("latin-1")
        return str(value)
    return None


def verify_webhook(
    payload: str | bytes,
    headers: Mapping[str, Any] | Iterable[tuple[str, str]],
    secret: str | Iterable[str],
    *,
    tolerance_seconds: int = DEFAULT_WEBHOOK_TOLERANCE_SECONDS,
    now: int | None = None,
) -> WebhookEvent:
    """Verifies a webhook delivery and returns the parsed event.

    Pass the request body exactly as received (``str`` or ``bytes``), before any JSON parsing.
    ``secret`` may be a list to accept several secrets (for example while you roll out a new one).
    Raises :class:`WebhookVerificationError` when headers are missing, the timestamp is outside the
    tolerance or no signature matches.
    """
    secrets = [secret] if isinstance(secret, str) else [s for s in secret if s]
    if not secrets or not all(secrets):
        raise WebhookVerificationError("Missing webhook secret")

    event_id = _header(headers, WEBHOOK_ID_HEADER)
    timestamp_header = _header(headers, WEBHOOK_TIMESTAMP_HEADER)
    signature_header = _header(headers, WEBHOOK_SIGNATURE_HEADER)
    if not event_id or not timestamp_header or not signature_header:
        raise WebhookVerificationError("Missing webhook id, timestamp or signature header")

    if not timestamp_header.strip().isdigit():
        raise WebhookVerificationError("Invalid webhook timestamp")
    timestamp = int(timestamp_header.strip())
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > tolerance_seconds:
        raise WebhookVerificationError("Webhook timestamp is outside the tolerance")

    body = payload.encode("utf-8") if isinstance(payload, str) else payload
    signed = f"{timestamp}.".encode() + body
    given = [part[3:] for part in _SEPARATOR.split(signature_header) if part.startswith("v1=")]
    matched = False
    for candidate in secrets:
        expected = hmac.new(candidate.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        for value in given:
            if hmac.compare_digest(value, expected):
                matched = True
    if not matched:
        raise WebhookVerificationError("No matching webhook signature")

    try:
        event = json.loads(body)
    except ValueError as error:
        raise WebhookVerificationError("Webhook body is not valid JSON") from error
    if not isinstance(event, dict) or event.get("id") != event_id:
        raise WebhookVerificationError("Webhook id header does not match the body")
    return cast(WebhookEvent, event)
