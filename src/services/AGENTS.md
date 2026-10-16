# src/services DOX

## Purpose

- Multi-step flows that combine scrapers, downloads, embedders and datastores; today only `OmniPipeline`, the post processing behind `POST /process/all`

## Ownership

- `omni_pipeline.py` — `OmniPipeline`: scrape → download → embed → store → finalize for posts already claimed as `IN_PROCESS`, plus the module-level `_EMBED_LOCK`
- `schemas.py` — `PipelineStage`, `EmbeddingItem`, `PostJob` (per-post state), and `ProcessingAccepted` (the `/process/all` response model)

## Local Contracts

- Stage order is fixed:
  1. `LinkScraper.scrap_bulk`.
  2. `download_and_save_file` into an `aiofiles` `TemporaryDirectory` under `TEMP_DIR_PATH`, deleted after embedding.
  3. One `asyncio.to_thread` call to `OmniEmbeddingManager.encode_inputs` with every item of every active post.
  4. One `QdrantManager.upsert_vectors` into `get_collection(GEMMA2_OMNI)`.
  5. `PostgresManager.set_status`.
- One vector per item: the caption (`text`, `media_index` 0), every image and every video. Posts with no text and no media fail at `scrape` as `empty_post`
- Failure is per post: a post stops at its first failed stage (any failed download fails the whole post) and the rest continue. An exception escaping a stage fails every post still active at that stage
- Every claimed post ends `SUCCESS` (vectors stored) or `FAILED`; `_finalize` runs in `finally`. `run()` never raises, because it runs as a background task
- Model use is serialised by `_EMBED_LOCK`, a `threading.Lock`. Never use an `asyncio.Semaphore` here (see `db/postgres/AGENTS.md`)
- Classes log via `LoggerMixin`. Each stage logs `Stage started` / `Stage finished` with `active_posts`, `failed_in_stage` and `duration_ms`. Each failed post logs `Post failed` with `post_id`, `url`, `platform`, `stage` and `reason`. The run ends with a `Pipeline finished` summary. All lines carry the request's `log_id`, which the background task and `to_thread` inherit

## Work Guidance

- New flows go in their own module here with their own stage enum, and get their dependencies injected from the route (managers, `aiohttp` session); never build clients here

## Verification

- `make server`, `POST /save`, then `POST /process/all` with an `X-Request-ID` header. Grep the server log for that id: every stage must appear, and `psql` must show no `in_process` rows once `Pipeline finished` is logged
