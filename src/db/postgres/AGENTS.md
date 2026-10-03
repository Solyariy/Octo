# src/db/postgres DOX

## Purpose

- Relational storage for users and submitted media files, over SQLAlchemy async with asyncpg

## Ownership

- `init_db.py` — `Base`, `get_base_metadata()` for Alembic, and `postgres_lifespan()`, the async CM yielding `(engine, async_sessionmaker)`
- `models.py` — `UserPostgres`, `MediaFilePostgres`
- `schemas.py` — `UserInfo`, `MediaFile` pydantic shapes returned to callers
- `manager.py` — `PostgresManager`

## Local Contracts

- Settings: `POSTGRES_URL`, `POSTGRES_ECHO`, and the `POSTGRES_POOL_*` / `POSTGRES_MAX_OVERFLOW` family in `db_settings`. Storage is the `pgdata` compose volume
- `PostgresManager` takes an `async_sessionmaker` and opens one short-lived session per statement; it rolls back and re-raises on failure. Add query methods here rather than opening sessions in call sites
- Concurrency is capped by the engine pool (`POSTGRES_POOL_SIZE=10`, `MAX_OVERFLOW=0`), never by a semaphore: an `asyncio.Semaphore` binds permanently to the first event loop that contends on it, breaking any later `asyncio.run()` in the same process. Pool exhaustion raises `TimeoutError` after `POSTGRES_POOL_TIMEOUT` rather than blocking forever
- Do not give routes a request-scoped session. `POST /process/all` downloads media and runs blocking inference mid-request; a session held across that would pin a pooled connection idle-in-transaction and deadlock the service at `POSTGRES_POOL_SIZE` concurrent requests
- `postgres_lifespan()` runs `SELECT 1` on entry because `create_async_engine` connects lazily; without it a bad `POSTGRES_URL` would only surface on the first request
- `Base` is a plain `DeclarativeBase`, not `MappedAsDataclass`: `mapped_column` must not use dataclass-only arguments (`default_factory`, `init`, `kw_only`) — use `default` for Python-side values and `server_default` for DB-side ones
- Schema changes go through Alembic, never by recreating tables; `alembic/env.py` reads `Base.metadata`, so every `models.py` edit needs a matching revision (see `alembic/AGENTS.md`)

## Verification

- `docker compose exec postgres psql -U octo -d octo -c "select count(*) from pg_stat_activity where datname='octo';"` must return 0 shortly after shutdown; a non-zero count means the engine was not disposed
