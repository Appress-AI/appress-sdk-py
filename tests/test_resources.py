from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from typing import Any

import pytest

from appress import Generation, WaitTimeoutError

from .conftest import Recorder, async_client, client, fail, generation, live_session, ok, turn


def multipart_fields(body: bytes) -> dict[str, bytes]:
    """Minimal multipart parser for assertions: part name -> raw content."""
    boundary = body.split(b"\r\n", 1)[0]
    fields = {}
    for part in body.split(boundary)[1:-1]:
        head, _, content = part.partition(b"\r\n\r\n")
        name = head.split(b'name="', 1)[1].split(b'"', 1)[0].decode()
        fields[name] = content[: -len(b"\r\n")]
    return fields


class TestGenerationsCreate:
    def test_sends_a_json_body_with_wire_field_names(self) -> None:
        recorder = Recorder(ok(generation(), status=202))
        created = client(recorder).generations.create(
            feature_type="NEWS",
            input_text="hello",
            feature_params={"news_lang": "en", "tone": "Objective", "news_category": "technology"},
        )
        assert created["status"] == "PENDING"
        request = recorder.requests[0]
        assert request.method == "POST"
        assert request.url.path == "/v1/generations"
        assert recorder.json() == {
            "featureType": "NEWS",
            "inputText": "hello",
            "featureParams": {"news_lang": "en", "tone": "Objective", "news_category": "technology"},
        }
        assert len(request.headers["idempotency-key"]) == 36

    def test_uploads_a_path_as_multipart_with_feature_params_as_json(self, tmp_path: Path) -> None:
        path = tmp_path / "interview.mp3"
        path.write_bytes(b"ID3audio")
        recorder = Recorder(ok(generation(featureType="TRANSCRIPTION", inputType="FILE"), status=202))
        client(recorder).generations.create(feature_type="TRANSCRIPTION", file=path, feature_params={"stt_lang": "tr"})
        body = recorder.bodies[0]
        fields = multipart_fields(body)
        assert fields["featureType"] == b"TRANSCRIPTION"
        assert json.loads(fields["featureParams"]) == {"stt_lang": "tr"}
        assert fields["file"] == b"ID3audio"
        assert b'filename="interview.mp3"' in body
        assert b"Content-Type: audio/mpeg" in body

    def test_uploads_in_memory_data_with_a_file_name(self) -> None:
        recorder = Recorder(ok(generation(), status=202))
        client(recorder).generations.create(feature_type="PROOFREADING", file=("draft.txt", b"Merhaba"))
        body = recorder.bodies[0]
        assert multipart_fields(body)["file"] == b"Merhaba"
        assert b'filename="draft.txt"' in body
        assert b"Content-Type: text/plain" in body

    def test_resends_the_whole_file_on_retry(self, tmp_path: Path) -> None:
        path = tmp_path / "a.wav"
        path.write_bytes(b"RIFFdata")
        recorder = Recorder(fail(503, "busy"), ok(generation(), status=202))
        client(recorder).generations.create(feature_type="TRANSCRIPTION", file=str(path))
        assert [multipart_fields(body)["file"] for body in recorder.bodies] == [b"RIFFdata", b"RIFFdata"]
        assert recorder.requests[0].headers["idempotency-key"] == recorder.requests[1].headers["idempotency-key"]

    def test_sends_an_open_file_whole_on_every_attempt(self) -> None:
        stream = io.BytesIO(b"PAYLOAD")
        stream.name = "/tmp/doc.pdf"
        stream.seek(3)
        recorder = Recorder(fail(502, "bad gateway"), ok(generation(), status=202))
        client(recorder).generations.create(feature_type="PROOFREADING", file=stream)
        assert [multipart_fields(body)["file"] for body in recorder.bodies] == [b"PAYLOAD", b"PAYLOAD"]
        assert b'filename="doc.pdf"' in recorder.bodies[0]

    def test_sends_event_mode_without_an_input(self) -> None:
        recorder = Recorder(ok(generation(), status=202))
        client(recorder).generations.create(
            feature_type="PRESS_RELEASE",
            feature_params={
                "mode": "event",
                "event": {
                    "description": "Launch",
                    "news_category": "technology",
                    "tone": "Objective",
                    "language": "en",
                },
            },
        )
        assert "inputText" not in recorder.json()
        assert recorder.json()["featureParams"]["mode"] == "event"

    @pytest.mark.parametrize(
        "inputs",
        [{}, {"input_text": "a", "input_url": "https://b"}],
    )
    def test_requires_exactly_one_input(self, inputs: dict[str, Any]) -> None:
        recorder = Recorder(ok(generation()))
        with pytest.raises(ValueError, match="exactly one"):
            client(recorder).generations.create(feature_type="NEWS", **inputs)
        assert recorder.requests == []

    def test_rejects_an_input_in_event_mode(self) -> None:
        recorder = Recorder(ok(generation()))
        with pytest.raises(ValueError, match="Event mode"):
            client(recorder).generations.create(
                feature_type="NEWS",
                input_text="a",
                feature_params={
                    "mode": "event",
                    "event": {"description": "d", "news_category": "sports", "tone": "Objective", "language": "tr"},
                },
            )

    def test_raw_bytes_need_a_file_name(self) -> None:
        with pytest.raises(TypeError, match="file name"):
            client(Recorder(ok(generation()))).generations.create(feature_type="PROOFREADING", file=b"data")


class TestWaitForCompletion:
    def test_polls_until_a_final_status_and_reports_progress(self, sleeps: list[float]) -> None:
        recorder = Recorder(
            ok(generation(status="PROCESSING", progress={"step": "processing", "percent": 40})),
            ok(generation(status="PROCESSING", progress={"step": "processing", "percent": 80})),
            ok(generation(status="COMPLETED", result={"ops": [{"insert": "done\n"}]})),
        )
        seen: list[Generation] = []
        done = client(recorder).generations.wait_for_completion("abc", on_progress=seen.append)
        assert done["status"] == "COMPLETED"
        assert [g["progress"]["percent"] for g in seen] == [40, 80, None]
        assert sleeps == [2.0, 3.0]

    def test_returns_error_without_raising(self) -> None:
        recorder = Recorder(ok(generation(status="ERROR", error="Failed")))
        done = client(recorder).generations.wait_for_completion("abc")
        assert done["status"] == "ERROR"
        assert done.get("error") == "Failed"

    def test_raises_wait_timeout_error_when_the_limit_is_reached(self) -> None:
        recorder = Recorder(ok(generation(status="PROCESSING")))
        with pytest.raises(WaitTimeoutError) as info:
            client(recorder).generations.wait_for_completion("abc", wait_timeout=0)
        assert info.value.resource_id == "abc"

    def test_create_and_wait(self) -> None:
        recorder = Recorder(ok(generation(), status=202), ok(generation(status="COMPLETED")))
        done = client(recorder).generations.create_and_wait(feature_type="NEWS", input_text="hello")
        assert done["status"] == "COMPLETED"
        assert [r.method for r in recorder.requests] == ["POST", "GET"]
        assert "idempotency-key" not in recorder.requests[1].headers


class TestIterate:
    def test_walks_every_page(self) -> None:
        items = [generation(id=str(i)) for i in range(5)]
        recorder = Recorder(
            ok({"items": items[:2], "total": 5}),
            ok({"items": items[2:4], "total": 5}),
            ok({"items": items[4:], "total": 5}),
        )
        ids = [g["id"] for g in client(recorder).generations.iterate(take=2)]
        assert ids == ["0", "1", "2", "3", "4"]
        assert [r.url.params["skip"] for r in recorder.requests] == ["0", "2", "4"]


class TestLiveTranscriptions:
    def test_create_and_extend_send_an_idempotency_key_and_wire_names(self) -> None:
        recorder = Recorder(ok(live_session(), status=202))
        appress = client(recorder)
        appress.live_transcriptions.create(url="https://youtu.be/x", speaker_labels=True, max_duration_minutes=60)
        appress.live_transcriptions.extend("s1", total_duration_minutes=180)
        assert recorder.json(0) == {"url": "https://youtu.be/x", "speakerLabels": True, "maxDurationMinutes": 60}
        assert recorder.json(1) == {"totalDurationMinutes": 180}
        assert recorder.requests[1].url.path == "/v1/live-transcriptions/s1/extend"
        assert all("idempotency-key" in r.headers for r in recorder.requests)

    def test_stop_sends_no_idempotency_key(self) -> None:
        recorder = Recorder(ok(live_session(state="COMPLETED")))
        client(recorder).live_transcriptions.stop("s1")
        assert recorder.requests[0].url.path == "/v1/live-transcriptions/s1/stop"
        assert "idempotency-key" not in recorder.requests[0].headers

    def test_options_active_and_extend_options_paths(self) -> None:
        recorder = Recorder(ok({}))
        appress = client(recorder)
        appress.live_transcriptions.options()
        appress.live_transcriptions.active()
        appress.live_transcriptions.extend_options("s1")
        assert [r.url.path for r in recorder.requests] == [
            "/v1/live-transcriptions/options",
            "/v1/live-transcriptions/active",
            "/v1/live-transcriptions/s1/extend-options",
        ]

    def test_stream_turns_yields_each_final_turn_once_and_ends_with_the_session(self) -> None:
        recorder = Recorder(
            ok(live_session(turns=[turn("t1", "Hel", False)])),
            ok(live_session(turns=[turn("t1", "Hello", True), turn("t2", "Wor", False, 2)])),
            ok(live_session(state="COMPLETED", turns=[turn("t1", "Hello", True), turn("t2", "World", True, 2)])),
        )
        texts = [t["text"] for t in client(recorder).live_transcriptions.stream_turns("s1")]
        assert texts == ["Hello", "World"]
        assert len(recorder.requests) == 3

    def test_stream_turns_with_include_partial_also_yields_interim_text(self) -> None:
        recorder = Recorder(
            ok(live_session(turns=[turn("t1", "Hel", False)])),
            ok(live_session(turns=[turn("t1", "Hel", False)])),
            ok(live_session(state="COMPLETED", turns=[turn("t1", "Hello", True)])),
        )
        stream = client(recorder).live_transcriptions.stream_turns("s1", include_partial=True)
        assert [(t["text"], t["isFinal"]) for t in stream] == [("Hel", False), ("Hello", True)]


class TestAsyncClient:
    def test_create_and_wait(self, sleeps: list[float]) -> None:
        recorder = Recorder(
            ok(generation(), status=202), ok(generation(status="PROCESSING")), ok(generation(status="COMPLETED"))
        )
        progress: list[str] = []

        async def on_progress(g: Generation) -> None:
            progress.append(g["status"])

        async def run() -> Generation:
            async with async_client(recorder) as appress:
                return await appress.generations.create_and_wait(
                    feature_type="NEWS", input_text="hello", on_progress=on_progress
                )

        done = asyncio.run(run())
        assert done["status"] == "COMPLETED"
        assert progress == ["PROCESSING", "COMPLETED"]
        assert sleeps == [2.0]

    def test_retries_with_the_same_idempotency_key(self, sleeps: list[float]) -> None:
        recorder = Recorder(fail(429, "slow", headers={"Retry-After": "2"}), ok(live_session(), status=202))

        async def run() -> None:
            async with async_client(recorder) as appress:
                await appress.live_transcriptions.create(url="https://youtu.be/x")

        asyncio.run(run())
        assert sleeps == [2.0]
        assert recorder.requests[0].headers["idempotency-key"] == recorder.requests[1].headers["idempotency-key"]

    def test_iterate_and_stream_turns(self) -> None:
        recorder = Recorder(
            ok({"items": [generation(id="a")], "total": 1}),
            ok(live_session(state="COMPLETED", turns=[turn("t1", "Hi", True)])),
        )

        async def run() -> tuple[list[str], list[str]]:
            async with async_client(recorder) as appress:
                ids = [g["id"] async for g in appress.generations.iterate()]
                texts = [t["text"] async for t in appress.live_transcriptions.stream_turns("s1")]
                return ids, texts

        assert asyncio.run(run()) == (["a"], ["Hi"])
