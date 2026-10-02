# appress-sdk-py — contributor notes

## Rules

- Public repository (MIT). No commit, push or PyPI publish without explicit maintainer instruction. A published version number can never be reused.
- English only: commits (Conventional Commits), branches, PRs, release notes, comments, docstrings, error messages, tests, docs.
- This repo documents the public API only. Describe what an endpoint accepts and returns, never how the service produces it.
- The SDK follows the published API contract; it never defines it. Keep features in step with `@appress/sdk` (JavaScript).

## Release

Bump `src/appress/_version.py` and CHANGELOG, push, then publish a GitHub Release tagged `v<version>`. `.github/workflows/publish.yml` publishes to PyPI with Trusted Publishing (OIDC, environment `pypi`). `ci.yml` runs lint, mypy and tests on Python 3.10–3.14 and the contract check (also weekly).

## Code

- `src/appress/_http.py`: request engine for `SyncHTTP`/`AsyncHTTP` (`{success,data}` unwrap, error mapping, retries on 408/429/502/503/504 and network errors with `Retry-After`, per-request timeout). `sleep`/`async_sleep` are module attributes so tests can replace them.
- `src/appress/resources/`: `generations`, `live_transcriptions`, each with a sync and an async class. Arguments are snake_case; the `*_FIELDS` maps translate them to the wire fields and are read by `scripts/check_contract.py`.
- Responses are plain dicts typed with `TypedDict` (`_types.py`), keyed like the JSON. Unknown fields pass through; do not add validation that rejects them.
- `_constants.py`: `Literal` enums (tuples derive from them). `_errors.py`: class per status + `code`.
- Billable POSTs (`generations.create`, `live_transcriptions.create`, `extend`) always send `Idempotency-Key`, reused on every retry of one logical call. Do not regress this.

## Contract

- OpenAPI: `GET https://api.appress.ai/api-reference/openapi.json`
- Limits, enums, feature params, error codes: `GET https://api.appress.ai/api-reference/config`

## Commands

Set up once: `python3 -m venv .venv && .venv/bin/pip install -e . --group dev` (pip ≥ 25.1).

| Purpose | Command |
| --- | --- |
| Lint / format | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` |
| Type check (strict) | `.venv/bin/mypy` |
| Tests (mock transport, no network) | `.venv/bin/pytest` |
| Contract drift vs the published OpenAPI | `.venv/bin/python scripts/check_contract.py` (or `<url-or-file>`) |
| Build sdist + wheel | `.venv/bin/python -m build` |

- Tests never call the real API. `examples/` spend real API credit.
- On contract drift, update `_types.py`/`_constants.py`/resources and field maps, README and CHANGELOG together and bump the version per semver.
- Don't commit `dist/`, `.venv/` or caches.
