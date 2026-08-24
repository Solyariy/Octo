# src/db DOX

## Purpose

- Client and session factories for every datastore Octo talks to

## Ownership

- `postgres.py` — async SQLAlchemy engine, `async_sessionmaker`, `get_db()` FastAPI dependency
- `qdrant.py` — shared `AsyncQdrantClient` via `get_client()` / `close_client()`
- `chroma.py` — throwaway in-memory Chroma prototype that runs its own queries at import time; not wired into the app
- `lance.py` — empty placeholder for a LanceDB client

## Local Contracts

- One module per datastore; a module exposes accessors, never a connected client as an import side effect (`chroma.py` violates this and must not be imported by application code)
- Clients are module-level singletons created lazily and reused; `qdrant.py` pairs `get_client()` with `close_client()` and any new client must offer the same shutdown hook
- Connection settings live in local `BaseSettings` classes in this package (`database_url`, `qdrant_url`, `qdrant_api_key`, `qdrant_prefer_grpc`), read from the environment with no prefix — they are deliberately separate from `src.settings.MainSettings`
- Defaults target the `docker-compose.yml` services: Postgres at `db:5432` (`octo`/`octo`/`octo`), Qdrant at `localhost:6333` with storage in `./qdrant_data`
- No ORM models, migrations, or collection schemas exist yet; adding them means adding structure here and updating this doc

## Work Guidance

- Expose datastore access to routes through FastAPI dependencies like `get_db`, not by importing engines directly

## Verification

- No automated checks; `docker compose up db qdrant-db` is the only way to exercise these clients
