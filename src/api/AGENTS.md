# src/api DOX

## Purpose

- The HTTP surface of Octo: route definitions, request/response schemas, and the FastAPI dependencies routes resolve against

## Ownership

- `router.py` — `main_router`, the single `APIRouter` mounted by `src.main`; holds `GET /health`, `POST /save`, `POST /process/all`, `GET /posts/{post_id}`, `GET /search`, and includes `tasks_router`
- `tasks.py` — `tasks_router` (prefix `/api/tasks`): `GET /api/tasks`, `GET /api/tasks/{task_id}`, `POST /api/tasks/{task_id}/retry`
- `schemas.py` — request bodies exchanged with clients (`InputPost`: `url` validated by `LinkScraper.classify_platform`, computed `platform`)
- `responses.py` — API-only response shapes: `SearchHit` (post + score + matched `modality`/`media_index`), `SearchPage` (a fastapi-pagination `Page` without `total`) and `TaskPage` (with `total`)
- `middleware.py` — `trace_requests`, the HTTP middleware that logs each request's span and returns its `log_id` as the `X-Request-ID` response header. It never sets `LOG_ID` itself: its first log line triggers `get_log_id()`, which binds a fresh UUID. Incoming `X-Request-ID` headers are ignored
- `dependencies.py` — the `app.state` accessors (`get_aiohttp_client`, `get_qdrant_manager`, `get_postgres_manager`, `get_embedder`) and the `Annotated` aliases routes actually use: `AiohttpClientDep`, `QdrantManagerDep`, `PostgresManagerDep`, `EmbedderDep`
- `auth/` — JWT issuing (`POST /auth/token`), `AuthManager`, `get_current_user` and `CurrentUserDep`

## Local Contracts

- `src.main` includes only `main_router`; sub-routers (`tasks_router`) are included by `main_router`, and routes are never declared in `main.py`
- Long-lived clients are created once in the `lifespan` of `src.main`, stored on `app.state`, and reached only through the `Depends` accessors here — never by importing a client module inside a route
- Routes declare dependencies through the `*Dep` aliases and never construct a manager themselves. Managers are cheap, stateless wrappers around a connection; one per request is intentional
- Keep the accessors `async def`: a sync `def` dependency costs a threadpool hop for what is a bare attribute read
- Response models come from `src.db.postgres.schemas`, `src.services.schemas` (`ProcessingAccepted`), `src.utils.annotations` or `responses.py`; `schemas.py` holds only what clients send
- `get_current_user` converts any lookup failure into `401`; it never leaks the underlying exception
- Routes hold no pipeline logic: multi-step work lives in `src.services`, and routes only claim rows and schedule it
- Query filters are fastapi-filter models from `src.db.qdrant.filters`, injected with `FilterDepends`; they never carry `user_id`, which routes add server-side. Unknown query params are ignored by FastAPI, not rejected
- Pagination uses fastapi-pagination `Params` (`page`, `size` ≤ 100) and `SearchPage.create(items, params=params)`. Do not call `add_pagination`: fastapi-pagination 0.15.16 crashes against FastAPI 0.139 (`get_body_field` signature)
- Adding, removing or changing a route or its params also updates the matching request in `postman/collections/Octo/` (see `postman/AGENTS.md`)
- Every request is traced: read the id only through `get_log_id()`, never set or reset `LOG_ID` inside a route, or the request's logs split across ids

## Work Guidance

- `POST /save` takes a non-empty list of `InputPost`. Any url no scraper supports fails the whole request with `422`. Rows are inserted as `PENDING` with `on_conflict_do_nothing` on the unique `url`, so duplicates are skipped and absent from the returned ids
- `POST /process/all` atomically claims the user's `PENDING` posts as `IN_PROCESS` and records the batch as a `tasks` row tagged with its `log_id`. It returns `202 ProcessingAccepted(log_id, task_id, post_ids)` and runs `OmniPipeline.run` as a `BackgroundTasks` task, or returns `200` with `task_id: null` and empty `post_ids` when nothing is pending. Progress is visible through logs (`log_id`), `GET /api/tasks/{task_id}` and `GET /posts/{post_id}`
- `GET /api/tasks` pages the caller's tasks newest first (`Params`, `TaskPage` with `total`). `GET /api/tasks/{task_id}` returns `TaskDetail`: every post with its `status`, failed `stage` and `error` in that task. Missing and other users' tasks answer `404 Task not found`
- `POST /api/tasks/{task_id}/retry` answers `409` unless the task's status is `failed`, then re-claims its posts still `FAILED` as a new task and returns `202 ProcessingAccepted` with the new `task_id`; `409 No failed posts left to retry` when none remain
- `GET /posts/{post_id}` returns the caller's `Post`; a missing post and another user's post both answer `404 Post not found`
- `GET /search?q=` embeds `q` with the shared embedder (`prompt_name="SearchQuery"`, under `EMBED_LOCK`), ranks the caller's posts in Qdrant by best-matching point with `PointFilter` applied there, then hydrates them from Postgres (rows gone from Postgres are dropped). `page * size` above `SEARCH_MAX_DEPTH` (1000) answers 422, because grouped queries re-rank every earlier page

## Verification

- `docker compose up --build`, then `GET localhost:8000/health` must return `{"ok": true}`
- No automated checks; manual end-to-end flow in `src/services/AGENTS.md`
