# Changelog

## Unreleased

- `expected_language` accepts `"auto"` (detects the spoken language, which may change during the session) or one of the supported language codes listed in the API reference; other values are rejected with a 400 error.

## 0.1.0 — 2026-10-02

- First version, matching the features of `@appress/sdk` 0.4.0:
  `generations` (create, retrieve, list, iterate, wait_for_completion, create_and_wait) and
  `live_transcriptions` (options, active, create, retrieve, stop, extend_options, extend, stream_turns).
- Sync `Appress` and asyncio `AsyncAppress` clients.
- Automatic `Idempotency-Key`, retry/backoff with `Retry-After`, typed errors, file upload from path/file/bytes.
- Result helpers: `get_result_text`, `get_speaker_turns`, `get_timed_words`.
- Published value lists: `LIVE_TRANSCRIPTION_FAILURE_CODES`, `GENERATION_PROGRESS_STEPS`, `ERROR_CODES`.
