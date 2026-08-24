# src DOX

## Purpose

- All runtime application code for Octo: a FastAPI ingestion service that turns submitted content into embeddings and stores them in vector and relational databases

## Ownership

- Owns `main.py` (FastAPI app, routes, uvicorn entrypoint) and `settings.py` (`MainSettings`, `LOG_ID`)
- Owns cross-package conventions listed below; delegates domain detail to `db/`, `embedders/`, `utils/`

## Local Contracts

- `src` is an import package rooted at the repository root: always use absolute imports (`from src.utils.logs import LoggerMixin`), never relative
- Every module is runnable as `uv run python -m src.<path>`; no `sys.path` manipulation
- Configuration comes from pydantic-settings classes reading `.env`; secrets are never hardcoded. `MainSettings.HF_AUTH_TOKEN` is required, so importing `src.settings` fails without `.env`
- `MODELS_PATH` (default `<repo>/models`) is the only on-disk model cache location; resolve paths through `src.utils.order.get_model_path`
- Logging goes through `src.utils.logs`, never `print` or bare `logging` in library code; `print` is acceptable only in `__main__` demo blocks and manual test scripts
- New dependencies must be added to `pyproject.toml`; `transformers` is pinned to 4.x and `torchcodec` must stay uninstalled (see the root DOX)

## Work Guidance

- The service is early-stage: routes in `main.py` accept `SaveData` and only log it, no persistence pipeline is wired yet. Do not assume an existing ingestion flow
- Async is the default for I/O (asyncpg, SQLAlchemy async, `AsyncQdrantClient`); model inference in `embedders/` is synchronous and blocking

## Verification

- `docker compose up --build` starts the API on `:8000` with Postgres and Qdrant; `GET /` must return `{"ok": true}`
- No test runner, linter, or type checker is configured

## Child DOX Index

- `db/AGENTS.md` — database and vector-store clients, session/client lifecycle
- `embedders/AGENTS.md` — embedding model registry, download/cache manager, manual model checks
- `utils/AGENTS.md` — logging, type annotations, shared helpers
