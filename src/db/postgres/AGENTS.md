# src/db/postgres DOX

## Purpose

- Relational storage for users and submitted posts, over SQLAlchemy async with asyncpg

## Ownership

- `init_db.py` — `Base`, `get_base_metadata()` for Alembic, and `postgres_lifespan()`, the async CM yielding `(engine, async_sessionmaker)`
- `models.py` — `UserPostgres`, `PostPostgres` (`posts` table: `url`, `platform`, `status: ProcessingStatus`, `user_id`), `TaskPostgres` (`tasks` table: one row per claimed batch from `/process/all` or a retry — `request_id`, `user_id`, `success_count`, `failed_count`), `TaskPostPostgres` (`task_posts`: many-to-many task↔post, PK `(task_id, post_id)`, with the post's outcome in that task — `status`, failed `stage`, `error`), `ScraperStatusPostgres` (`scraper_statuses`: one row per unique `platform` — `last_request_status`, `updated_at`)
- `schemas.py` — `UserInfo`, `Post`, `PostIdUrl`, `Task` (with `total_count` and a computed `status`), `TaskPost`, `TaskDetail`, `ScraperStatus` pydantic shapes returned to callers
- `manager.py` — `PostgresManager`: user queries (`upsert_user` is used by `cli/postgres.py`), `insert_posts_bulk`, `claim_pending_posts`, `claim_failed_task_posts`, `finish_task`, user-scoped reads `get_post`/`get_task`/`get_task_detail` (None when missing or not the user's), `get_posts_by_ids` and `list_tasks`, maintenance read `get_posts_by_status`, `get_media_file_by_id_bulk`, `upsert_scraper_status` (on conflict by `platform`; called only by `LinkScraper`)

## Local Contracts

- Settings: `POSTGRES_URL`, `POSTGRES_ECHO`, and the `POSTGRES_POOL_*` / `POSTGRES_MAX_OVERFLOW` family in `db_settings`. Storage is the `pgdata` compose volume
- `PostgresManager` takes an `async_sessionmaker` and opens one short-lived session per statement; it rolls back and re-raises on failure. Add query methods here rather than opening sessions in call sites
- Concurrency is capped by the engine pool (`POSTGRES_POOL_SIZE=10`, `MAX_OVERFLOW=0`), never by a semaphore: an `asyncio.Semaphore` binds permanently to the first event loop that contends on it, breaking any later `asyncio.run()` in the same process. Pool exhaustion raises `TimeoutError` after `POSTGRES_POOL_TIMEOUT` rather than blocking forever
- Post status lifecycle: `PENDING` on insert → `IN_PROCESS` only via `claim_pending_posts` (a single `UPDATE ... RETURNING`, so concurrent callers never claim the same row) or `claim_failed_task_posts` (re-claims a task's posts that failed there and are still `FAILED`) → `SUCCESS`/`FAILED` via `finish_task`. Both claims are a single `UPDATE ... RETURNING`, so concurrent callers never claim the same row. Never select-then-update to claim
- A non-empty claim inserts a new `tasks` row plus one `IN_PROCESS` `task_posts` row per post in the same transaction, so a batch is never claimed without its record; a retry is always a new task. `finish_task` writes post statuses, each `task_posts` outcome and the task counts in one transaction
- Task status is never stored: `Task.status` is `in_process` while `success_count + failed_count < total_count` (count of its `task_posts`), else `failed` if any failed, else `success`. A task left `in_process` by a crashed server stays so; nothing reaps it and it cannot be retried `tasks.request_id` is the request's `log_id` (a server-generated UUID from `get_log_id()`, also returned as `X-Request-ID`), stored as an indexed string column
- Do not give routes a request-scoped session. `POST /process/all` downloads media and runs blocking inference mid-request; a session held across that would pin a pooled connection idle-in-transaction and deadlock the service at `POSTGRES_POOL_SIZE` concurrent requests
- `postgres_lifespan()` runs `SELECT 1` on entry because `create_async_engine` connects lazily; without it a bad `POSTGRES_URL` would only surface on the first request
- `Base` is a plain `DeclarativeBase`, not `MappedAsDataclass`: `mapped_column` must not use dataclass-only arguments (`default_factory`, `init`, `kw_only`) — use `default` for Python-side values and `server_default` for DB-side ones
- Schema changes go through Alembic, never by recreating tables; `alembic/env.py` reads `Base.metadata`, so every `models.py` edit needs a matching revision (see `alembic/AGENTS.md`)

## Verification

- `docker compose exec postgres psql -U octo -d octo -c "select count(*) from pg_stat_activity where datname='octo';"` must return 0 shortly after shutdown; a non-zero count means the engine was not disposed
