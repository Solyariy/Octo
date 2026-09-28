# src/db DOX

## Purpose

- Client factories and query managers for every datastore Octo talks to

## Ownership

- Owns the shape every datastore package follows and the rules shared by all of them; delegates datastore detail to `postgres/` and `qdrant/`
- `config.py` — empty placeholder

## Local Contracts

- One package per datastore, each shaped as `init_db` / `models` / `schemas` / `manager`
- Connection settings come from `src.settings.db_settings`; this package defines none of its own. Every one has a default, so `.env` may omit them all
- Defaults target a local stack (`localhost:5432` / `localhost:6333`); `docker-compose.yml` overrides the app container to the `postgres` and `qdrant` service hostnames
- No module here builds a connected client at import time. Each datastore exposes an app-scoped `@asynccontextmanager` entered once by `src.main`'s `AsyncExitStack`; any new datastore must follow that shape
- Managers take an already-built connection object in their constructor and never reach for a global

## Work Guidance

- Routes never touch this package directly: they depend on the `QdrantManagerDep` / `PostgresManagerDep` aliases in `src.api.dependencies`, which build a manager per request over the connection on `app.state`

## Verification

- No automated checks; `docker compose up postgres qdrant` is the only way to exercise these clients

## Child DOX Index

- `postgres/AGENTS.md` — async engine lifecycle, ORM models, `PostgresManager`, pool and session rules
- `qdrant/AGENTS.md` — `AsyncQdrantClient` lifecycle, collection registry and safe initialisation, `QdrantManager`
