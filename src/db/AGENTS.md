# src/db DOX

## Purpose

- Client and session factories for every datastore Octo talks to

## Ownership

- `postgres/` — `init_db.py` (async engine, `postgres_async_session`, `get_postgres_client()` dependency, `Base`), `models.py` (ORM models), `schemas.py`, `manager.py`
- `qdrant/` — `init_db.py` (lazy shared `AsyncQdrantClient` via `get_qdrant_client()` / `close_qdrant_client()` / `get_qdrant_context_manager()`, plus `init_qdrant_collections()`), `models.py` (collection definitions in `COLLECTIONS`), `schemas.py`, `manager.py`

## Local Contracts

- One package per datastore, each shaped as `init_db` / `models` / `schemas` / `manager`; a module exposes accessors, never a connected client as an import side effect
- Clients are module-level singletons created lazily and reused; Qdrant pairs `get_qdrant_client()` with `close_qdrant_client()` and any new client must offer the same shutdown hook
- Connection settings come from `src.settings.db_settings` (`postgres_url`, `qdrant_url`, `qdrant_api_key`, `qdrant_prefer_grpc`); this package defines no settings of its own
- Defaults target the `docker-compose.yml` services: Postgres at `db:5432` (`octo`/`octo`/`octo`), Qdrant at `localhost:6333` with storage in `./qdrant_data`
- `Base` is a plain `DeclarativeBase`, not `MappedAsDataclass`: `mapped_column` must not use dataclass-only arguments (`default_factory`, `init`, `kw_only`) — use `default` for Python-side values and `server_default` for DB-side ones
- Qdrant collections are created idempotently by `init_qdrant_collections()`; no Postgres migration tool exists yet, so schema changes mean recreating tables

## Work Guidance

- Expose datastore access to routes through FastAPI dependencies like `get_db`, not by importing engines directly

## Verification

- No automated checks; `docker compose up db qdrant-db` is the only way to exercise these clients
