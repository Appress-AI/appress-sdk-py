from __future__ import annotations

import pytest

from appress import (
    APIConnectionError,
    APIError,
    Appress,
    AppressError,
    BadRequestError,
    ConcurrencyLimitError,
    ConflictError,
    IdempotencyConflictError,
    InsufficientCreditError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    __version__,
)

from .conftest import Recorder, client, fail, generation, network_error, ok


class TestClientSetup:
    def test_raises_a_clear_error_without_an_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APPRESS_API_KEY", raising=False)
        with pytest.raises(AppressError, match="APPRESS_API_KEY"):
            Appress()

    def test_reads_the_key_and_base_url_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APPRESS_API_KEY", "apr_live_env")
        monkeypatch.setenv("APPRESS_BASE_URL", "https://env.test")
        with Appress() as appress:
            assert appress._http.api_key == "apr_live_env"
            assert appress._http.base_url == "https://env.test"


class TestRequestAndResponse:
    def test_sends_headers_and_unwraps_the_envelope(self) -> None:
        recorder = Recorder(ok(generation()))
        result = client(recorder).generations.retrieve("abc")
        request = recorder.requests[0]
        assert result["id"] == generation()["id"]
        assert str(request.url) == "https://api.test/v1/generations/abc"
        assert request.headers["authorization"] == "Bearer apr_live_test"
        assert request.headers["accept"] == "application/json"
        assert request.headers["user-agent"].startswith(f"appress-sdk-python/{__version__} python/")
        assert "idempotency-key" not in request.headers

    def test_keeps_a_path_prefix_in_base_url(self) -> None:
        recorder = Recorder(ok(generation()))
        client(recorder, base_url="https://gateway.test/appress/").generations.retrieve("a/b")
        assert str(recorder.requests[0].url) == "https://gateway.test/appress/v1/generations/a%2Fb"

    def test_adds_list_query_parameters_only_when_set(self) -> None:
        recorder = Recorder(ok({"items": [], "total": 0}))
        client(recorder).generations.list(take=5, status="COMPLETED", api_key_id="key-1")
        assert dict(recorder.requests[0].url.params) == {"take": "5", "status": "COMPLETED", "apiKeyId": "key-1"}

    def test_default_and_extra_headers(self) -> None:
        recorder = Recorder(ok(generation()))
        appress = client(recorder, default_headers={"X-Team": "a"})
        appress.generations.retrieve("abc", extra_headers={"X-Trace": "t"})
        assert recorder.requests[0].headers["x-team"] == "a"
        assert recorder.requests[0].headers["x-trace"] == "t"

    def test_raw_request(self) -> None:
        recorder = Recorder(ok({"version": 1}))
        assert client(recorder).request("get", "/api-reference/config") == {"version": 1}
        assert recorder.requests[0].method == "GET"


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("status", "code", "cls"),
        [
            (400, None, BadRequestError),
            (403, None, PermissionDeniedError),
            (404, None, NotFoundError),
            (409, None, ConflictError),
            (409, "IDEMPOTENCY_KEY_CONFLICT", IdempotencyConflictError),
            (409, "CONCURRENT_GENERATION_LIMIT", ConcurrencyLimitError),
            (500, None, InternalServerError),
            (418, None, APIError),
        ],
    )
    def test_maps_status_and_code_to_a_class(self, status: int, code: str | None, cls: type[APIError]) -> None:
        recorder = Recorder(fail(status, "boom", code))
        with pytest.raises(cls) as info:
            client(recorder).generations.retrieve("abc")
        assert type(info.value) is cls
        assert info.value.status == status
        assert info.value.code == code
        assert info.value.message == "boom"
        assert str(info.value) == "boom"

    def test_a_403_credit_error_is_both_permission_denied_and_insufficient_credit(self) -> None:
        recorder = Recorder(fail(403, "Yetersiz API kredisi", "INSUFFICIENT_API_CREDIT"))
        with pytest.raises(InsufficientCreditError) as info:
            client(recorder).generations.retrieve("abc")
        assert isinstance(info.value, PermissionDeniedError)

    def test_builds_a_useful_message_from_a_non_json_body(self) -> None:
        import httpx

        recorder = Recorder(lambda _: httpx.Response(400, text="Bad gateway text"))
        with pytest.raises(BadRequestError, match="Bad gateway text") as info:
            client(recorder).generations.retrieve("abc")
        assert info.value.body == "Bad gateway text"


class TestRetries:
    def test_on_429_waits_for_retry_after_and_keeps_the_idempotency_key(self, sleeps: list[float]) -> None:
        recorder = Recorder(fail(429, "slow down", "RATE_LIMIT_EXCEEDED", {"Retry-After": "3"}), ok(generation()))
        client(recorder).generations.create(feature_type="NEWS", input_text="hello")
        assert len(recorder.requests) == 2
        assert sleeps == [3.0]
        keys = {request.headers["idempotency-key"] for request in recorder.requests}
        assert len(keys) == 1

    def test_raises_the_last_error_once_retries_are_exhausted(self, sleeps: list[float]) -> None:
        recorder = Recorder(fail(503, "busy", headers={"Retry-After": "1"}))
        with pytest.raises(InternalServerError):
            client(recorder, max_retries=2).generations.retrieve("abc")
        assert len(recorder.requests) == 3
        assert sleeps == [1.0, 1.0]

    def test_retries_network_errors_with_exponential_backoff(self, sleeps: list[float]) -> None:
        recorder = Recorder(network_error, network_error, ok(generation()))
        client(recorder).generations.retrieve("abc")
        assert len(recorder.requests) == 3
        assert 0.75 <= sleeps[0] <= 1.25
        assert 1.5 <= sleeps[1] <= 2.5

    def test_a_network_error_becomes_api_connection_error(self) -> None:
        recorder = Recorder(network_error)
        with pytest.raises(APIConnectionError):
            client(recorder, max_retries=0).generations.retrieve("abc")

    def test_does_not_retry_client_errors(self) -> None:
        recorder = Recorder(fail(400, "bad"))
        with pytest.raises(BadRequestError):
            client(recorder).generations.retrieve("abc")
        assert len(recorder.requests) == 1

    def test_lets_the_caller_pass_its_own_idempotency_key(self) -> None:
        recorder = Recorder(ok(generation()))
        client(recorder).generations.create(feature_type="NEWS", input_text="hello", idempotency_key="article-42")
        assert recorder.requests[0].headers["idempotency-key"] == "article-42"

    def test_rate_limit_error_exposes_retry_after(self) -> None:
        recorder = Recorder(fail(429, "slow down", headers={"Retry-After": "7"}))
        with pytest.raises(RateLimitError) as info:
            client(recorder, max_retries=0).generations.retrieve("abc")
        assert info.value.retry_after_seconds == 7.0
