# src/db DOX

## Purpose

- Client factories and query managers for every datastore Octo talks to

## Ownership

- `postgres/` — `init_db.py` (`postgres_lifespan()` async CM yielding `(engine, async_sessionmaker)`, `Base`, `get_base_metadata()` for Alembic), `models.py` (`UserPostgres`, `MediaFilePostgres`), `schemas.py` (`UserInfo`, `MediaFile`), `manager.py` (`PostgresManager`)
- `qdrant/` — `init_db.py` (`build_qdrant_client()`, the `qdrant_client_lifespan()` async CM, `init_qdrant_collections()`, `QdrantCollectionMismatchError`), `models.py` (`QdrantCollection` and the `QDRANT_COLLECTIONS` registry), `schemas.py`, `manager.py` (`QdrantManager`)

## Local Contracts

- One package per datastore, each shaped as `init_db` / `models` / `schemas` / `manager`; a module exposes accessors, never a connected client as an import side effect
- Connection settings come from `src.settings.db_settings` and this package defines none of its own: `QDRANT_URL`, `QDRANT_PREFER_GRPC`, `QDRANT_API_KEY`, `QDRANT_TIMEOUT`, `QDRANT_POOL_SIZE`, `QDRANT_CHECK_COMPATIBILITY`, `POSTGRES_URL`, `POSTGRES_ECHO`, and the `POSTGRES_POOL_*` family. Every one has a default, so `.env` may omit them all
- Defaults target a local stack (`localhost:5432` / `localhost:6333`); `docker-compose.yml` overrides the app container to the `postgres` and `qdrant` service hostnames. Qdrant storage is bind-mounted to `./qdrant_data`, Postgres to the `pgdata` volume
- `PostgresManager` takes an `async_sessionmaker` and opens one short-lived session per statement; it rolls back and re-raises on failure. Add query methods here rather than opening sessions in call sites
- Concurrency is capped by the engine pool (`POSTGRES_POOL_SIZE=10`, `MAX_OVERFLOW=0`), never by a semaphore: an `asyncio.Semaphore` binds permanently to the first event loop that contends on it, breaking any later `asyncio.run()` in the same process. Pool exhaustion raises `TimeoutError` after `POSTGRES_POOL_TIMEOUT` rather than blocking forever
- Do not give routes a request-scoped session. `POST /process/all` downloads media and runs blocking inference mid-request; a session held across that would pin a pooled connection idle-in-transaction and deadlock the service at `POSTGRES_POOL_SIZE` concurrent requests
- `QdrantManager` takes an already-built `AsyncQdrantClient` in its constructor: the app passes the one from `app.state`, so this package never reaches for the global inside a request
- No module here builds a connected client at import time. Each datastore exposes an app-scoped `@asynccontextmanager` (`postgres_lifespan`, `qdrant_client_lifespan`) entered once by `src.main`'s `AsyncExitStack`; any new datastore must follow that shape
- `qdrant_client_lifespan()` is app-scoped — never enter it inside a request. `AsyncQdrantClient` is not itself an async context manager, which is why the wrapper exists
- `postgres_lifespan()` runs `SELECT 1` on entry because `create_async_engine` connects lazily; without it a bad `POSTGRES_URL` would only surface on the first request
- `QDRANT_COLLECTIONS` is keyed by `EmbeddersEnum`, and each collection is sized from `member.get_dim()` — never a literal
- `init_qdrant_collections()` creates what is missing and validates what exists; it **never deletes**. A size/distance mismatch raises `QdrantCollectionMismatchError` and aborts startup so the operator migrates deliberately. There must be no `delete_collection` call anywhere in this package
- Pass `vectors_config=` a real `VectorParams`, never `**collection.model_dump()`: a flattened dump reaches the gRPC path as a *named-vectors* mapping and dies in `RestToGrpc.convert_vectors_config`
- Catch collection-creation failures on both `UnexpectedResponse` and `grpc.RpcError`, then re-probe `collection_exists()` instead of matching a status code — that distinguishes a lost create race between gunicorn workers from a spec the server rejected
- `Base` is a plain `DeclarativeBase`, not `MappedAsDataclass`: `mapped_column` must not use dataclass-only arguments (`default_factory`, `init`, `kw_only`) — use `default` for Python-side values and `server_default` for DB-side ones
- Postgres schema changes go through Alembic, never by recreating tables; `alembic/env.py` reads `Base.metadata`, so every `models.py` edit needs a matching revision (see `alembic/AGENTS.md`)

## Work Guidance

- Routes never touch this package directly: they depend on the `QdrantManagerDep` / `PostgresManagerDep` aliases in `src.api.dependencies`, which build a manager per request over the connection on `app.state`
- `QdrantManager.upsert_vectors` stores bare vectors under random ids with no payload, so points carry no link back to `media_files`. Adding that payload is the prerequisite for any search or delete-by-source feature

## Verification

- No automated checks; `docker compose up postgres qdrant` is the only way to exercise these clients
- Collection safety is checked by hand: plant a mismatched `cosmos_zero` (`size 512`, `Cosine`), start the app, and confirm it exits non-zero with `QdrantCollectionMismatchError` and leaves the collection untouched
- `docker compose exec postgres psql -U octo -d octo -c "select count(*) from pg_stat_activity where datname='octo';"` must return 0 shortly after shutdown; a non-zero count means the engine was not disposed
