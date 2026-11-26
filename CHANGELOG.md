# Changelog

## 0.2.0 — 2026-11-26

- `live_transcriptions.create()` accepts `translation_languages` (set at creation, up to `options()["translation"]["maxLanguages"]`). Each turn has `translations` keyed by language (`status`: `pending` | `completed` | `failed`, `text` when completed); sessions and active sessions list `translationLanguages`. `options()` returns `translation.languages`, `translation.maxLanguages` and `translationReservedCostUsdPerLanguage` per duration. New types `LiveTranscriptionTurnTranslation` and `LiveTranslationOptions`.
- Webhooks: `verify_webhook(raw_body, headers, secret)` verifies a delivery (`Appress-Webhook-Signature`, timestamp tolerance 300 s by default) and returns the typed `WebhookEvent`; raises `WebhookVerificationError`. New `WEBHOOK_EVENT_TYPES` and `WEBHOOK_TEST_EVENT_TYPE`.
- New error codes: `LIVE_TRANSLATION_INVALID_LANGUAGE`, `LIVE_TRANSLATION_SAME_LANGUAGE`, `LIVE_TRANSLATION_LIMIT_REACHED`.
- `LiveTranscriptionPlatform` is `"youtube"` | `"x"`; the API never returned `"microphone"` for API sessions.
- `DiarizationParams` accepts `stt_lang` (source audio language) and `translate_lang` (the interview is translated into this language). Translated interviews keep one op per speaker turn with `speaker`, `start`, `end`, `color`, without `words`; turns with no translatable content are omitted. `translate_lang` takes a language code such as `en`, `ar` or `pt-BR`.
- `expected_language` accepts `"auto"` (detects the spoken language, which may change during the session) or one of the supported language codes listed in the API reference; other values are rejected with a 400 error.

## 0.1.0 — 2026-10-02

- First version, matching the features of `@appress/sdk` 0.4.0:
  `generations` (create, retrieve, list, iterate, wait_for_completion, create_and_wait) and
  `live_transcriptions` (options, active, create, retrieve, stop, extend_options, extend, stream_turns).
- Sync `Appress` and asyncio `AsyncAppress` clients.
- Automatic `Idempotency-Key`, retry/backoff with `Retry-After`, typed errors, file upload from path/file/bytes.
- Result helpers: `get_result_text`, `get_speaker_turns`, `get_timed_words`.
- Published value lists: `LIVE_TRANSCRIPTION_FAILURE_CODES`, `GENERATION_PROGRESS_STEPS`, `ERROR_CODES`.
