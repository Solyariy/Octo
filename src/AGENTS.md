# src DOX

## Purpose

- All runtime application code for Octo: a FastAPI ingestion service that turns submitted media into embeddings and stores them in vector and relational databases

## Ownership

- Owns `main.py` (FastAPI app, `lifespan`, uvicorn entrypoint) and `settings.py` (`MainSettings`, `DBSettings`, `LOG_ID`)
- Owns cross-package conventions listed below; delegates domain detail to `api/`, `db/`, `embedders/`, `link_scrapers/`, `utils/`

## Local Contracts

- `src` is an import package rooted at the repository root: always use absolute imports (`from src.utils.logs import LoggerMixin`), never relative
- Modules are importable from the repository root with no `sys.path` manipulation. No CLI `main()`, `argparse` or `__main__` blocks here except the server entrypoint in `main.py`; hand-run scripts go in `cli/` (see `cli/AGENTS.md`)
- Configuration comes from pydantic-settings classes reading `.env`; secrets are never hardcoded. `MainSettings` has no defaults for `HF_AUTH_TOKEN`, `SECRET_KEY`, `ALGORITHM` and `ACCESS_TOKEN_EXPIRE_MINUTES`, so importing `src.settings` fails without a `.env` supplying all four
- `MODELS_PATH` (default `<repo>/models`) is the only on-disk model cache location; resolve paths through `src.utils.order.get_model_path`. Scratch files go under `TEMP_DIR_PATH` (`<repo>/temp`, gitignored); `INSTAGRAM_TEMP_DIR_PATH` (`temp/instagram`) and `THREADS_TEMP_DIR_PATH` (`temp/threads`) are the per-platform scratch subfolders
- `main.py` declares no routes: it includes `src.api.router.main_router` and owns process-wide startup/shutdown
- `lifespan` is the single owner of every connection. It drives an `AsyncExitStack` so resources unwind in reverse order on any failure — including one raised out of `yield` — and publishes four entries on `app.state`: `postgres_engine`, `postgres_sessionmaker`, `qdrant_client`, `aiohttp_client`. Datastore packages must expose an async CM to enter here, never a connected client at import time
- Logging goes through `src.utils.logs`, never `print` or bare `logging`
- New dependencies must be added to `pyproject.toml`; `transformers` is pinned to 4.x and `torchcodec` must stay uninstalled (reasons in `embedders/AGENTS.md`)

## Work Guidance

- Async is the default for I/O (asyncpg, SQLAlchemy async, `AsyncQdrantClient`, aiohttp, aiofiles); model loading and inference in `embedders/` is synchronous and blocking, so routes offload it with `asyncio.to_thread`
- Authentication settings exist in `MainSettings` but no token issuing or verification is implemented; `get_current_user` currently trusts a `user_id` supplied by the caller. Do not describe any endpoint as authenticated

## Verification

- `docker compose up --build` starts the API on `:8000` with Postgres and Qdrant; `GET /health` must return `{"ok": true}`
- No test runner or type checker is configured; fix imports with `uv run ruff check --fix src`, then format with `uv run yapf -ir src`

## Child DOX Index

- `api/AGENTS.md` — HTTP routes, request schemas, FastAPI dependencies
- `db/AGENTS.md` — shared datastore rules; delegates to `db/postgres/AGENTS.md` and `db/qdrant/AGENTS.md`
- `embedders/AGENTS.md` — embedding model registry, backend managers, manual model checks
- `link_scrapers/AGENTS.md` — resolving social-media URLs (Instagram, Threads) to fetchable media
- `utils/AGENTS.md` — logging, type annotations, download and video helpers
