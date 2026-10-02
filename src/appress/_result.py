from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any, TypedDict

from ._types import TimedWord

if sys.version_info >= (3, 11):
    from typing import NotRequired
else:
    from typing_extensions import NotRequired


class SpeakerTurn(TypedDict):
    speaker: str
    start: str
    end: str
    color: str
    words: NotRequired[list[TimedWord]]
    text: str


def _ops(result: Mapping[str, Any] | None) -> list[Any]:
    if not isinstance(result, Mapping):
        return []
    ops = result.get("ops")
    return ops if isinstance(ops, list) else []


def get_result_text(result: Mapping[str, Any] | None) -> str:
    """Plain text of a generation result (concatenated text inserts)."""
    return "".join(op["insert"] for op in _ops(result) if isinstance(op, dict) and isinstance(op.get("insert"), str))


def get_speaker_turns(result: Mapping[str, Any] | None) -> list[SpeakerTurn]:
    """DIARIZATION result as speaker turns. Ops without a ``speaker`` attribute are skipped."""
    turns: list[SpeakerTurn] = []
    for op in _ops(result):
        if not isinstance(op, dict) or not isinstance(op.get("insert"), str):
            continue
        attributes = op.get("attributes")
        if not isinstance(attributes, dict) or not isinstance(attributes.get("speaker"), str):
            continue
        turn: SpeakerTurn = {
            "speaker": attributes["speaker"],
            "start": attributes.get("start") or "",
            "end": attributes.get("end") or "",
            "color": attributes.get("color") or "",
            "text": op["insert"].strip(),
        }
        if attributes.get("words"):
            turn["words"] = attributes["words"]
        turns.append(turn)
    return turns


def get_timed_words(result: Mapping[str, Any] | None) -> list[TimedWord]:
    """Every word timing in a TRANSCRIPTION or DIARIZATION result, in order.

    Empty when no word timings are available or the transcript was translated.
    """
    words: list[TimedWord] = []
    for op in _ops(result):
        attributes = op.get("attributes") if isinstance(op, dict) else None
        if isinstance(attributes, dict) and isinstance(attributes.get("words"), list):
            words.extend(attributes["words"])
    return words
