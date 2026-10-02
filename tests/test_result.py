from __future__ import annotations

from typing import Any

from appress import get_result_text, get_speaker_turns, get_timed_words

TRANSCRIPT: dict[str, Any] = {
    "ops": [
        {
            "insert": "Good morning.\n",
            "attributes": {
                "start": "00:01",
                "end": "00:02",
                "words": [{"t": "Good", "s": 1.02, "e": 1.3}, {"t": "morning.", "s": 1.3, "e": 1.9}],
            },
        },
        {"insert": "Untimed line.\n"},
        {"insert": {"image": "x"}},
    ]
}

INTERVIEW: dict[str, Any] = {
    "ops": [
        {
            "insert": "Welcome to the show. \n",
            "attributes": {"speaker": "A", "start": "00:00", "end": "00:02", "color": "#123456"},
        },
        {
            "insert": "Thanks.\n",
            "attributes": {
                "speaker": "B",
                "start": "00:02",
                "end": "00:03",
                "color": "#654321",
                "words": [{"t": "Thanks.", "s": 2.1, "e": 2.6}],
            },
        },
        {"insert": "\n"},
    ]
}


def test_get_result_text_joins_text_inserts() -> None:
    assert get_result_text(TRANSCRIPT) == "Good morning.\nUntimed line.\n"


def test_get_result_text_tolerates_missing_or_malformed_results() -> None:
    assert get_result_text(None) == ""
    assert get_result_text({}) == ""
    assert get_result_text({"ops": "nope"}) == ""


def test_get_timed_words_returns_word_timings_in_order() -> None:
    assert [w["t"] for w in get_timed_words(TRANSCRIPT)] == ["Good", "morning."]
    assert get_timed_words(None) == []


def test_get_speaker_turns_maps_interview_ops_to_turns() -> None:
    assert get_speaker_turns(INTERVIEW) == [
        {"speaker": "A", "start": "00:00", "end": "00:02", "color": "#123456", "text": "Welcome to the show."},
        {
            "speaker": "B",
            "start": "00:02",
            "end": "00:03",
            "color": "#654321",
            "text": "Thanks.",
            "words": [{"t": "Thanks.", "s": 2.1, "e": 2.6}],
        },
    ]
