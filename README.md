# appress

Official Python client for the [Appress](https://appress.ai) public API.

- Automatic `Idempotency-Key` on every billable request, preserved across retries, so a retry is never charged twice.
- Retries with exponential backoff on `429`, `503`, timeouts and network failures (honours `Retry-After`).
- `wait_for_completion()` polling helper and `stream_turns()` for live transcription.
- File upload from a path, an open file or bytes. Paths are streamed from disk, not loaded into memory.
- Sync (`Appress`) and `asyncio` (`AsyncAppress`) clients with the same methods.
- Fully typed (`TypedDict` responses, `Literal` enums, `py.typed`). Python 3.10+, one runtime dependency (`httpx`).

> **Server-side only.** Your API key grants access to your wallet. Never ship it to a browser or a mobile app.

## Install

```bash
pip install appress
```

## Quick start

```python
from appress import Appress

appress = Appress()  # reads APPRESS_API_KEY

news = appress.generations.create_and_wait(
    feature_type="NEWS",
    input_text="Appress announced a new version of its AI-powered content platform.",
    feature_params={"news_lang": "en", "tone": "Objective", "news_category": "technology"},
)

if news["status"] == "COMPLETED":
    print(news["result"])
else:
    print(news["status"], news.get("error"))
```

Generations are asynchronous. `create()` returns immediately with `status: "PENDING"`;
`wait_for_completion()` polls (2 s, backing off to 10 s) until `COMPLETED`, `ERROR` or `CANCELLED`.
`ERROR`/`CANCELLED` are returned, not raised: check `status`.

Responses are plain `dict` objects keyed exactly like the API JSON (`featureType`, `actualCostUsd`, …),
so the [API reference](https://api.appress.ai/api-reference/openapi.json) applies as is. Method arguments
are snake_case.

### asyncio

```python
from appress import AsyncAppress

async with AsyncAppress() as appress:
    job = await appress.generations.create(feature_type="NEWS", input_url="https://…")
    done = await appress.generations.wait_for_completion(job["id"])
```

## Configuration

```python
appress = Appress(
    api_key="…",  # default: APPRESS_API_KEY
    base_url="https://api.appress.ai",  # default: APPRESS_BASE_URL or https://api.appress.ai
    timeout=60.0,  # seconds per request; file uploads default to 30 min
    max_retries=4,  # 408/429/502/503/504 and network errors
)
```

Every method also accepts per-call `timeout`, `max_retries` and `extra_headers`.
Pass `http_client=httpx.Client(...)` for proxies or custom transports. Use the client as a context
manager (`with Appress() as appress:`) or call `close()` to release connections.

## Generations

| Feature | `feature_type` | Inputs |
| --- | --- | --- |
| Transcription | `TRANSCRIPTION` | file, URL |
| Interview editor (diarization) | `DIARIZATION` | file, URL |
| Proofreading | `PROOFREADING` | file, text |
| News | `NEWS` | file, URL, text, or event mode |
| Press release | `PRESS_RELEASE` | file, URL, text, or event mode |

Send exactly one of `input_text`, `input_url` or `file`. Live, current limits and parameter lists
are published at [`GET /api-reference/config`](https://api.appress.ai/api-reference/config).

### File upload

```python
# From a path: streamed from disk.
job = appress.generations.create(
    feature_type="TRANSCRIPTION",
    file="./interview.mp3",
    feature_params={"stt_lang": "tr"},
)

# From memory, or from an open file.
appress.generations.create(feature_type="PROOFREADING", file=("draft.docx", data))
with open("draft.docx", "rb") as f:
    appress.generations.create(feature_type="PROOFREADING", file=f)
```

### Event mode (no input)

```python
appress.generations.create(
    feature_type="PRESS_RELEASE",
    feature_params={
        "mode": "event",
        "event": {
            "description": "Product launch in Istanbul",
            "news_category": "technology",
            "tone": "Objective",
            "language": "en",
        },
    },
)
```

### Poll, list, iterate

```python
job = appress.generations.create(feature_type="NEWS", input_url="https://…")

done = appress.generations.wait_for_completion(
    job["id"],
    wait_timeout=20 * 60,  # seconds; None for no limit
    on_progress=lambda g: print(g["status"], g["progress"]["percent"]),
)

page = appress.generations.list(status="COMPLETED", take=50)

for g in appress.generations.iterate(feature_type="TRANSCRIPTION"):
    print(g["id"], g["actualCostUsd"])
```

### Reading results

`result` is a [Quill Delta](https://quilljs.com/docs/delta/) document (`{"ops": [...]}`). Helpers cover the common cases:

```python
from appress import get_result_text, get_speaker_turns, get_timed_words

text = get_result_text(done.get("result"))  # plain text, any feature

turns = get_speaker_turns(interview.get("result"))  # DIARIZATION
# [{"speaker": "A", "start": "00:00", "end": "00:02", "text": "Welcome…", "color": "…"}]

words = get_timed_words(transcript.get("result"))  # TRANSCRIPTION / DIARIZATION
# [{"t": "Good", "s": 1.02, "e": 1.3}, …]  seconds from the start of the audio
```

| Feature | Line attributes |
| --- | --- |
| `TRANSCRIPTION` | `start`, `end` (`MM:SS`) and `words: [{t, s, e}]` on lines aligned to the audio. Not present when the transcript was translated (`translate_lang`) or no word timings are available. |
| `DIARIZATION` | One op per speaker turn: `speaker`, `start`, `end`, `color`, optional `words`. |
| `PROOFREADING` | Corrected text, plus `result["diff"]` (delta ops from input to output). |
| `NEWS` / `PRESS_RELEASE` | Formatting attributes (bold, italic, …); quote anchors are in `generation["quoteAnchors"]`. |

New attributes and response fields may be added over time; ignore the ones you don't use.

## Live transcription

```python
options = appress.live_transcriptions.options()

session = appress.live_transcriptions.create(
    url="https://www.youtube.com/watch?v=…",
    max_duration_minutes=60,
    speaker_labels=True,
)

for turn in appress.live_transcriptions.stream_turns(session["id"]):
    print(f"[{turn['speaker'] or '-'}] {turn['text']}")
```

`stream_turns` yields each finalised turn once and ends when the session is `COMPLETED` or `FAILED`.
Pass `include_partial=True` for interim text. Breaking out of the loop does **not** stop the
session: call `stop(id)`. Use `extend_options(id)` / `extend(id, total_duration_minutes=…)` to extend.

A `FAILED` session carries `failureCode` (one of `LIVE_TRANSCRIPTION_FAILURE_CODES`, e.g. `SOURCE_UNAVAILABLE`)
and a human-readable `failureMessage`. New codes may be added; treat unknown ones as a generic failure.

## Idempotency

`create()` and `extend()` send a fresh UUID `Idempotency-Key`, reused on automatic retries.
If your own job queue may re-run the same logical request, pass a stable key derived from your record:

```python
appress.generations.create(..., idempotency_key=f"article-{article.id}")
```

Same key + same body returns the original generation; same key + different body raises `IdempotencyConflictError`.

## Errors

```python
from appress import APIError, InsufficientCreditError, RateLimitError

try:
    appress.generations.create(...)
except InsufficientCreditError:
    ...  # top up; nothing was charged
except RateLimitError as err:
    ...  # retries exhausted; err.retry_after_seconds
except APIError as err:
    print(err.status, err.code, err.message)
```

| Class | HTTP | Retried |
| --- | --- | --- |
| `BadRequestError` | 400 | no |
| `AuthenticationError` | 401 | no |
| `PermissionDeniedError` / `InsufficientCreditError` | 403 | no |
| `NotFoundError` | 404 | no |
| `ConflictError` / `IdempotencyConflictError` / `ConcurrencyLimitError` | 409 | no |
| `PayloadTooLargeError` | 413 | no |
| `RateLimitError` | 429 | yes |
| `InternalServerError` | 5xx | 502/503/504 only |
| `APIConnectionError` / `APITimeoutError` | none | yes |

`err.code` carries a stable machine-readable code (e.g. `CONCURRENT_GENERATION_LIMIT`); `err.message`
is human-readable (Turkish) and may change. Every SDK error derives from `AppressError`.

## Escape hatch

```python
config = appress.request("GET", "/api-reference/config")
```

## License

MIT
