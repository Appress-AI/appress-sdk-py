"""Run: APPRESS_API_KEY=... python examples/live.py <stream-url>

NOTE: reserves API credit for the chosen duration. Ctrl+C stops the session.
"""

import sys

from appress import Appress

if len(sys.argv) < 2:
    sys.exit("Usage: examples/live.py <stream-url>")

with Appress() as appress:
    session = appress.live_transcriptions.create(url=sys.argv[1], max_duration_minutes=15)
    print("Session:", session["id"])
    try:
        for turn in appress.live_transcriptions.stream_turns(
            session["id"],
            on_session=lambda s: s["state"] == "FAILED" and print(s["failureCode"], s["failureMessage"]),
        ):
            print(f"[{turn['speaker'] or '-'}] {turn['text']}")
    except KeyboardInterrupt:
        appress.live_transcriptions.stop(session["id"])
