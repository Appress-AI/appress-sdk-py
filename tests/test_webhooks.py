from __future__ import annotations

import pytest

from appress import WebhookVerificationError, verify_webhook

# Shared test vector (the JavaScript SDK uses the same values).
SECRET = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
PREVIOUS_SECRET = "whsec_OLDSECRETOLDSECRETOLDSECRETOLDSE"
TIMESTAMP = 1795694400
RAW_BODY = (
    '{"id":"evt_00000000-0000-4000-8000-000000000001","type":"generation.completed",'
    '"createdAt":"2026-11-26T12:00:00.000Z","data":{"object":"generation",'
    '"id":"11111111-1111-4111-8111-111111111111","featureType":"TRANSCRIPTION","status":"COMPLETED",'
    '"apiKeyId":"22222222-2222-4222-8222-222222222222","completedAt":"2026-11-26T11:59:58.000Z"}}'
)
SIGNATURE = "bb2237b87769b7d49c0ec6ac6216fa12c7ad4ccb9bf77b799fbb2a604be8cbf0"
PREVIOUS_SIGNATURE = "563a9f76d8af60fa2a03a4328bea05469e20dddf668a99321a86070bb5ac9e4e"


def headers(signature: str = f"v1={SIGNATURE}", timestamp: int = TIMESTAMP) -> dict[str, str]:
    return {
        "Appress-Webhook-Id": "evt_00000000-0000-4000-8000-000000000001",
        "Appress-Webhook-Timestamp": str(timestamp),
        "Appress-Webhook-Signature": signature,
    }


def test_accepts_a_valid_delivery_and_returns_the_event() -> None:
    event = verify_webhook(RAW_BODY, headers(), SECRET, now=TIMESTAMP + 10)
    assert event["type"] == "generation.completed"
    assert event["data"]["object"] == "generation"


def test_accepts_bytes_header_pairs_and_either_signature_during_rotation() -> None:
    both = list(headers(f"v1={SIGNATURE} v1={PREVIOUS_SIGNATURE}").items())
    assert verify_webhook(RAW_BODY.encode(), both, PREVIOUS_SECRET, now=TIMESTAMP)["id"].startswith("evt_")
    assert verify_webhook(RAW_BODY.encode(), both, [SECRET], now=TIMESTAMP)


@pytest.mark.parametrize(
    ("body", "secret", "now"),
    [
        (RAW_BODY.replace("COMPLETED", "FAILED"), SECRET, TIMESTAMP),
        (RAW_BODY, "whsec_wrong", TIMESTAMP),
        (RAW_BODY, SECRET, TIMESTAMP + 301),
    ],
)
def test_rejects_modified_body_wrong_secret_and_stale_timestamp(body: str, secret: str, now: int) -> None:
    with pytest.raises(WebhookVerificationError):
        verify_webhook(body, headers(), secret, now=now)


def test_rejects_missing_headers_and_mismatched_id() -> None:
    with pytest.raises(WebhookVerificationError, match="Missing"):
        verify_webhook(RAW_BODY, {"Appress-Webhook-Timestamp": str(TIMESTAMP)}, SECRET, now=TIMESTAMP)
    with pytest.raises(WebhookVerificationError, match="id"):
        verify_webhook(RAW_BODY, {**headers(), "Appress-Webhook-Id": "evt_other"}, SECRET, now=TIMESTAMP)
