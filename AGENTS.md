# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Splitting

- Split a code file when it holds more than one responsibility; past ~300 lines, re-check whether it does. Line count alone is never the reason to split
- Split a child AGENTS.md when it exceeds ~60 lines or when one subfolder's details dominate it: move those details into that subfolder's own AGENTS.md and leave a one-line entry in the parent's Child DOX Index. The parent keeps only rules shared by all its children
- Never split an AGENTS.md into sibling files (`AGENTS_<topic>.md`); every doc must be reachable by walking from the root to the target path
- The root AGENTS.md is exempt from the line limit because it carries the DOX protocol, but project detail that belongs to one subtree still moves down

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## Project

- Octo is a FastAPI service that accepts media URLs, embeds the media with local HuggingFace models, and stores vectors in Qdrant alongside relational data in Postgres
- Python 3.13, managed with `uv`; run everything as `uv run python -m src.<module>` from the repository root; `make server` starts the `postgres` and `qdrant` compose services detached, then runs the API locally (`src.main` on `localhost:8000`); `make clear [pg|qdrant]` stops the service(s) and deletes stored data (both when no argument), after which Postgres needs `alembic upgrade head` again
- Runtime config comes from `.env` via pydantic-settings. `HF_AUTH_TOKEN`, `SECRET_KEY`, `ALGORITHM` and `ACCESS_TOKEN_EXPIRE_MINUTES` have no defaults, so any import of `src.settings` fails without all four. Never commit `.env` or print secrets
- `docker compose up --build` brings up three services: `app` (`:8000`), `postgres` (`:5432`), and `qdrant` (`:6333`/`:6334`)
- Postgres schema lives in `src/db/postgres/models.py` and changes only through Alembic revisions under `alembic/versions/<year>/<month>/`
- Downloaded models live in `MODELS_PATH` (`<repo>/models`), Qdrant data in `./qdrant_data`, and per-request scratch files in `TEMP_DIR_PATH` (`<repo>/temp`); all three are local caches, never version them
- `transformers` stays pinned to `>=4.51,<5` and `torchcodec` stays uninstalled; both are required by the embedding stack (see `src/embedders/AGENTS.md`)
- The project is early-stage: `README.md` is empty, no test runner, type checker, or CI exists. Do not cite checks that are not configured
- Formatting is `uv run yapf -ir src alembic` (`[tool.yapf]`, PEP 8 base, 100 cols, 8-space continuation indent with dedented closing brackets); ruff only lints (`uv run ruff check`) and its `--fix` is limited to import sorting and unused-import removal (`I`, `F401`); `ruff format` is disabled via `exclude = ["*"]`. Order: `ruff check --fix`, then `yapf`
- `.idea/` is JetBrains state, not project material; leave it alone

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

## Child DOX Index

- `src/AGENTS.md` — all application code: FastAPI entrypoint, settings, and the `api`/`db`/`embedders`/`link_scrapers`/`utils` packages below it
- `alembic/AGENTS.md` — Postgres migration environment, revision layout, and the generate/apply workflow
- Root owns packaging (`pyproject.toml`, `uv.lock`), the `Makefile` (dev shortcuts), containerization (`Dockerfile`, `docker-compose.yml`, `.dockerignore`), `alembic.ini`, ignore files, and `README.md`
