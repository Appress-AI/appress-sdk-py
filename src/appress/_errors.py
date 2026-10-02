"""Error hierarchy.

Error envelope: ``{"success": false, "statusCode", "message", "code"?, "nextAction"?}``.
``code`` is a stable machine-readable value; ``message`` is human-readable text
(currently Turkish) and is not part of the contract.
"""

from __future__ import annotations

import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


class AppressError(Exception):
    """Base class of every error raised by the SDK."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class APIError(AppressError):
    """The server returned an HTTP error response."""

    status: int
    code: str | None
    """An ``ErrorCode`` value when known; newer API versions may add values."""
    headers: httpx.Headers
    body: Any
    """Raw response body (text when it is not JSON)."""

    def __init__(self, status: int, message: str, code: str | None, headers: httpx.Headers, body: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.headers = headers
        self.body = body


class BadRequestError(APIError):
    """400: validation error. Fix the request; do not retry it blindly."""


class AuthenticationError(APIError):
    """401: missing, invalid or revoked API key."""


class PermissionDeniedError(APIError):
    """403: not permitted or not enough credit."""


class InsufficientCreditError(PermissionDeniedError):
    """403 ``INSUFFICIENT_API_CREDIT``: not enough API credit. Nothing was charged; top up the wallet."""


class NotFoundError(APIError):
    """404: generation or session not found (or it belongs to another account)."""


class ConflictError(APIError):
    """409: conflict. See ``code`` for details."""


class IdempotencyConflictError(ConflictError):
    """409 ``IDEMPOTENCY_KEY_CONFLICT``: the same key was used with a different body."""


class ConcurrencyLimitError(ConflictError):
    """409 ``CONCURRENT_GENERATION_LIMIT``: your plan's concurrent generation limit is reached."""


class PayloadTooLargeError(APIError):
    """413: file or request body limit exceeded."""


class RateLimitError(APIError):
    """429: rate limited. The SDK retries automatically and raises once retries are exhausted."""

    @property
    def retry_after_seconds(self) -> float | None:
        """Wait time suggested by the server (seconds), if any."""
        return parse_retry_after_seconds(self.headers.get("retry-after"))


class InternalServerError(APIError):
    """5xx: server error."""


class APIConnectionError(AppressError):
    """Network error: the request did not reach the server or no response arrived."""


class APITimeoutError(APIConnectionError):
    """The request timed out."""


class WaitTimeoutError(AppressError):
    """``wait_for_completion`` did not reach a final status in time.

    The job may still be running on the server and can be awaited again with the same ID.
    """

    def __init__(self, message: str, resource_id: str) -> None:
        super().__init__(message)
        self.resource_id = resource_id


def parse_retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        pass
    else:
        return seconds if seconds >= 0 else None
    try:
        date = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, date.timestamp() - time.time())


def create_api_error(status: int, body: Any, headers: httpx.Headers) -> APIError:
    envelope = body if isinstance(body, dict) else {}
    raw_message = envelope.get("message")
    if isinstance(raw_message, str) and raw_message:
        message = raw_message
    elif isinstance(body, str) and body:
        message = body
    else:
        message = f"HTTP {status}"
    raw_code = envelope.get("code")
    code = raw_code if isinstance(raw_code, str) else None

    cls: type[APIError]
    if status == 400:
        cls = BadRequestError
    elif status == 401:
        cls = AuthenticationError
    elif status == 403:
        cls = InsufficientCreditError if code == "INSUFFICIENT_API_CREDIT" else PermissionDeniedError
    elif status == 404:
        cls = NotFoundError
    elif status == 409:
        if code == "IDEMPOTENCY_KEY_CONFLICT":
            cls = IdempotencyConflictError
        elif code == "CONCURRENT_GENERATION_LIMIT":
            cls = ConcurrencyLimitError
        else:
            cls = ConflictError
    elif status == 413:
        cls = PayloadTooLargeError
    elif status == 429:
        cls = RateLimitError
    elif status >= 500:
        cls = InternalServerError
    else:
        cls = APIError
    return cls(status, message, code, headers, body)
