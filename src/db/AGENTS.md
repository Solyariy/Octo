# src/db DOX

## Purpose

- Client factories and query managers for every datastore Octo talks to

## Ownership

- `postgres/` — `init_db.py` (async engine, `postgres_async_session`, `get_postgres_client()` dependency, `Base`, `get_base_metadata()` for Alembic), `models.py` (`UserPostgres`, `MediaFilePostgres`), `schemas.py` (`UserInfo`, `MediaFile`), `manager.py` (`PostgresManager`)
- `qdrant/` — `init_db.py` (lazy shared `AsyncQdrantClient` via `get_qdrant_client()` / `close_qdrant_client()` / `get_qdrant_context_manager()`, plus `init_qdrant_collections()`), `models.py` (`QdrantCollection` and the `QDRANT_COLLECTIONS` registry), `schemas.py`, `manager.py` (`QdrantManager`)

## Local Contracts

- One package per datastore, each shaped as `init_db` / `models` / `schemas` / `manager`; a module exposes accessors, never a connected client as an import side effect
- Connection settings come from `src.settings.db_settings`: `POSTGRES_URL`, `QDRANT_URL`, `QDRANT_PREFER_GRPC`. This package defines no settings of its own and there is no API-key setting for Qdrant
- Defaults target a local stack (`localhost:5432` / `localhost:6333`); `docker-compose.yml` overrides the app container to the `postgres` and `qdrant` service hostnames. Qdrant storage is bind-mounted to `./qdrant_data`, Postgres to the `pgdata` volume
- `PostgresManager` opens its own short-lived session per statement through `postgres_async_session` and caps concurrency with a class-level `asyncio.Semaphore(10)`; it rolls back and re-raises on failure. Add query methods here rather than opening sessions in call sites
- `QdrantManager` takes an already-built `AsyncQdrantClient` in its constructor: the app passes the one from `app.state`, so this package never reaches for the global inside a request
- The Qdrant client is a module-level singleton created lazily; `get_qdrant_client()` is paired with `close_qdrant_client()` and any new client must offer the same shutdown hook
- `QDRANT_COLLECTIONS` is keyed by `EmbeddersEnum`, and each collection is sized from `member.get_dim()` — never a literal. `init_qdrant_collections()` is idempotent and recreates a collection only when creation fails on an existing name
- `Base` is a plain `DeclarativeBase`, not `MappedAsDataclass`: `mapped_column` must not use dataclass-only arguments (`default_factory`, `init`, `kw_only`) — use `default` for Python-side values and `server_default` for DB-side ones
- Postgres schema changes go through Alembic, never by recreating tables; `alembic/env.py` reads `Base.metadata`, so every `models.py` edit needs a matching revision (see `alembic/AGENTS.md`)

## Work Guidance

- Routes reach Qdrant through `src.api.dependencies.get_qdrant_client` and Postgres through `PostgresManager`; `get_postgres_client()` exists as a session dependency but nothing uses it yet
- `QdrantManager.upsert_vectors` stores bare vectors under random ids with no payload, so points carry no link back to `media_files`. Adding that payload is the prerequisite for any search or delete-by-source feature

## Verification

- No automated checks; `docker compose up postgres qdrant` is the only way to exercise these clients
