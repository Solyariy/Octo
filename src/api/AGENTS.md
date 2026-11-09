# src/api DOX

## Purpose

- The HTTP surface of Octo: route definitions, request/response schemas, and the FastAPI dependencies routes resolve against

## Ownership

- `router.py` — `main_router`, the single `APIRouter` mounted by `src.main`; holds `GET /health`, `POST /save`, `POST /process/all`, `GET /posts/{post_id}`, `GET /search`
- `schemas.py` — request bodies exchanged with clients (`InputPost`: `url` validated by `LinkScraper.classify_platform`, computed `platform`)
- `responses.py` — API-only response shapes: `SearchHit` (post + score + matched `modality`/`media_index`) and `SearchPage`, a fastapi-pagination `Page` without `total`
- `middleware.py` — `trace_requests`, the HTTP middleware that binds `LOG_ID` from `X-Request-ID` (or a fresh UUID), logs each request's span and echoes `X-Request-ID`
- `dependencies.py` — the `app.state` accessors (`get_aiohttp_client`, `get_qdrant_manager`, `get_postgres_manager`, `get_embedder`) and the `Annotated` aliases routes actually use: `AiohttpClientDep`, `QdrantManagerDep`, `PostgresManagerDep`, `EmbedderDep`
- `auth/` — JWT issuing (`POST /auth/token`), `AuthManager`, `get_current_user` and `CurrentUserDep`

## Local Contracts

- One router (`main_router`); `src.main` only includes it, routes are never declared in `main.py`
- Long-lived clients are created once in the `lifespan` of `src.main`, stored on `app.state`, and reached only through the `Depends` accessors here — never by importing a client module inside a route
- Routes declare dependencies through the `*Dep` aliases and never construct a manager themselves. Managers are cheap, stateless wrappers around a connection; one per request is intentional
- Keep the accessors `async def`: a sync `def` dependency costs a threadpool hop for what is a bare attribute read
- Response models come from `src.db.postgres.schemas`, `src.services.schemas` (`ProcessingAccepted`), `src.utils.annotations` or `responses.py`; `schemas.py` holds only what clients send
- `get_current_user` converts any lookup failure into `401`; it never leaks the underlying exception
- Routes hold no pipeline logic: multi-step work lives in `src.services`, and routes only claim rows and schedule it
- Query filters are fastapi-filter models from `src.db.qdrant.filters`, injected with `FilterDepends`; they never carry `user_id`, which routes add server-side. Unknown query params are ignored by FastAPI, not rejected
- Pagination uses fastapi-pagination `Params` (`page`, `size` ≤ 100) and `SearchPage.create(items, params=params)`. Do not call `add_pagination`: fastapi-pagination 0.15.16 crashes against FastAPI 0.139 (`get_body_field` signature)
- Every request is traced: never reset or overwrite `LOG_ID` inside a route, or the request's logs split across ids

## Work Guidance

- `POST /save` takes a non-empty list of `InputPost`. Any url no scraper supports fails the whole request with `422`. Rows are inserted as `PENDING` with `on_conflict_do_nothing` on the unique `url`, so duplicates are skipped and absent from the returned ids
- `POST /process/all` atomically claims the user's `PENDING` posts as `IN_PROCESS`. It returns `202 ProcessingAccepted(log_id, post_ids)` and runs `OmniPipeline.run` as a `BackgroundTasks` task, or returns `200` with empty `post_ids` when nothing is pending. Progress is visible through logs (`log_id`) and `GET /posts/{post_id}`
- `GET /posts/{post_id}` returns the caller's `Post`; a missing post and another user's post both answer `404 Post not found`
- `GET /search?q=` embeds `q` with the shared embedder (`prompt_name="SearchQuery"`, under `EMBED_LOCK`), ranks the caller's posts in Qdrant by best-matching point with `PointFilter` applied there, then hydrates them from Postgres (rows gone from Postgres are dropped). `page * size` above `SEARCH_MAX_DEPTH` (1000) answers 422, because grouped queries re-rank every earlier page

## Verification

- `docker compose up --build`, then `GET localhost:8000/health` must return `{"ok": true}`
- No automated checks; manual end-to-end flow in `src/services/AGENTS.md`
