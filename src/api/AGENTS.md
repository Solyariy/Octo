# src/api DOX

## Purpose

- The HTTP surface of Octo: route definitions, request/response schemas, and the FastAPI dependencies routes resolve against

## Ownership

- `router.py` — `main_router`, the single `APIRouter` mounted by `src.main`; holds `GET /health`, `POST /save`, `POST /process/all`
- `schemas.py` — request bodies exchanged with clients (`InputMediaFile`)
- `dependencies.py` — the `app.state` accessors (`get_aiohttp_client`, `get_qdrant_manager`, `get_postgres_manager`), `get_current_user`, and the `Annotated` aliases routes actually use: `AiohttpClientDep`, `QdrantManagerDep`, `PostgresManagerDep`, `CurrentUserDep`

## Local Contracts

- One router (`main_router`); `src.main` only includes it, routes are never declared in `main.py`
- Long-lived clients are created once in the `lifespan` of `src.main`, stored on `app.state`, and reached only through the `Depends` accessors here — never by importing a client module inside a route
- Routes declare dependencies through the `*Dep` aliases and never construct a manager themselves. Managers are cheap, stateless wrappers around a connection; one per request is intentional
- Keep the accessors `async def`: a sync `def` dependency costs a threadpool hop for what is a bare attribute read
- Response models come from `src.db.postgres.schemas` (DB-facing shapes) or `src.utils.annotations`; `schemas.py` holds only what clients send
- `get_current_user` converts any lookup failure into `401`; it never leaks the underlying exception
- Blocking model work must go through `asyncio.to_thread` inside a `with get_embedding_manager(...)` block, as `POST /process/all` does — never call an embedder inline in an async route
- Downloads land in a `TemporaryDirectory` rooted at `main_settings.TEMP_DIR_PATH` and are deleted when the request ends; nothing persists to disk outside that tree

## Work Guidance

- `POST /process/all` is the reference ingestion flow: pull unprocessed rows for the user, download the media, embed clips with `COSMOS_EMBED1_448P`, upsert vectors to Qdrant, then flip `is_processed`. Keep that order — rows are only marked processed after the vectors land
- Vectors are upserted without a payload today, so a Qdrant point cannot yet be traced back to its `media_files` row; add the payload alongside any feature that needs the link
- `POST /save` is unauthenticated and inserts with `on_conflict_do_nothing` on the unique `url`, so duplicates are silently skipped and absent from the returned ids

## Verification

- `docker compose up --build`, then `GET localhost:8000/health` must return `{"ok": true}`
- No automated checks
