# cli DOX

## Purpose

- Hand-run CLI and smoke-test scripts that exercise `src` code from the terminal; nothing here is imported by the service

## Ownership

- `instagram_html.py` — fetches a reel/post via `src.link_scrapers.scrapers.instagram_html.fetch_reel` (permalink HTML, embed fallback), saves its video and description via `download_reel` to `main_settings.INSTAGRAM_TEMP_DIR_PATH / <shortcode> / {video.mp4, caption.txt}` (created) unless `--no-download`, prints `source`, author, counts, caption, thumbnail and saved paths; `--out` dumps the raw post node JSON; exits 1 on `InstagramFetchError` / `ScraperStatusError`
- `instagram_graphql.py` — same output, but fetches a reel/post via `src.link_scrapers.scrapers.instagram_graphql.fetch_reel`, saves its video and description via `download_reel` to `main_settings.INSTAGRAM_TEMP_DIR_PATH / <shortcode> / {video.mp4, caption.txt}` (created) unless `--no-download`, prints author, counts, caption and saved paths; `--out` dumps the raw GraphQL JSON; exits 1 on `InstagramFetchError` / `ScraperStatusError`
- `threads.py` — fetches a post via `src.link_scrapers.scrapers.threads.fetch_post`, prints it, downloads media via `download_media` to `main_settings.THREADS_TEMP_DIR_PATH / <shortcode>` (created) unless `--no-download`, `--out` dumps the raw post JSON
- `youtube.py` — fetches a video via `src.link_scrapers.scrapers.youtube.fetch_video`, downloads it via `download_video` to `main_settings.YOUTUBE_TEMP_DIR_PATH / <id>.<ext>` (created) unless `--no-download`, then prints title, channel, counts, resolution and description; `--out` dumps the raw yt-dlp info; exits 1 on `YouTubeFetchError`
- `link_scraper.py` — classifies the url and scrapes it via `src.link_scrapers.manager.LinkScraper.scrap`, prints the platform and the normalized `ScrapedPost` JSON, `--out` dumps that JSON; exits 1 on an unsupported url or a platform fetch error. No media download
- `embeddinggemma.py` — embeds a sample clip, a sample photo and four captions in one `OmniEmbeddingManager.encode_inputs` call; exits non-zero unless vectors are `output_dim`-wide and the clip and the photo each rank their own caption first. Reuses `download_video` from `nvidia_cosmos.py`
- `qwen.py` — loads `QWEN3_4B`, encodes three passages, exits non-zero if the paraphrase pair is not more similar than the unrelated pair
- `nvidia_cosmos.py` — runs only from `.venv-cosmos` (transformers 4.x, recipe in the root `AGENTS.md`); downloads a sample clip, embeds it and six captions through `CosmosEmbeddingManager`, exits non-zero if vectors are not `output_dim`-wide or the expected caption does not rank first; its `download_video` is a smoke-test helper, production downloads belong in `src.utils.basic`
- `postgres.py` — upserts the admin user (`--email`, default `admin@octo.local`; `--password`, default `admin`) straight into Postgres via `PostgresManager.upsert_user`; testing environments only, needs migrated tables (`alembic upgrade head`)
- `seeder.py` — reads `seed_urls.txt` (or `--file`; one url per line, `#` comments) and inserts the urls as `PENDING` posts owned by `--email` (default `admin@octo.local`) via `PostgresManager.insert_posts_bulk`; existing urls are skipped, exits 1 when the user is missing (run `make admin`). Needs migrated tables
- `seed_urls.txt` — the seed post urls; keep them stripped of share/tracking query params so the unique `posts.url` dedups them
- `qdrant_backfill.py` — copies `posts.created_at` into the Qdrant payload of every point of each `SUCCESS` post (`set_payload` filtered by `post_id`), after ensuring payload indexes; idempotent, `--dry-run` only lists. Needs Postgres and Qdrant up
- `embedder_registry.py` — prints every `EmbeddersEnum` member's backend, dim and load kwargs
- `recipe_bench.py` — recipe-parser benchmark over `src.recipe_parser.bench`: `prepare [--file]` scrapes + downloads reels to `temp/recipes/media/<shortcode>` (cached; aborts on `ScraperStatusError`), `download-models [--pipelines]` pre-fetches weights so timings exclude downloads, `run [--pipelines a,b] [--file] [--limit N]` prints a per-pipeline summary and writes `temp/recipes/runs/<UTC>/`, `list` prints `PIPELINES`
- `recipe_parser.py` — parses one reel (url, shortcode, or local video with `--caption-file`) through `RecipePipeline` with `--pipeline` or per-role `--asr/--ocr/--slm` overrides, `--force-av` to run audio+OCR after a caption hit; prints the `ParseResult` JSON, exits 1 without a recipe
- `seed_urls_recipies.txt` — the recipe test set: cooking reels whose recipe lives in the description, the audio or on-screen text; default `--file` of `recipe_bench.py`

## Local Contracts

- One script per file, named after the `src` module or model it exercises, run as `uv run python -m cli.<name>` from the repository root
- CLI entrypoints (`argparse`, `main()`, `if __name__ == "__main__"`) live here, never in `src`; `src` modules expose only library functions these scripts call
- Scripts import `src` with absolute imports and may open their own `aiohttp.ClientSession`; `print` is the output channel here
- Smoke scripts return an exit code from `main() -> int` (`raise SystemExit(main())`); they are not pytest cases

## Work Guidance

## Verification

- `uv run python -m cli.postgres [--email ...] [--password ...]` (`make admin [args="..."]`)
- `uv run python -m cli.seeder [--file ...] [--email ...]` (`make seed [file=...] [args="..."]`)
- `uv run python -m cli.embedder_registry`
- `uv run python -m cli.qdrant_backfill [--dry-run]`
- `uv run python -m cli.qwen`
- `uv run python -m cli.embeddinggemma`
- `.venv-cosmos/bin/python -m cli.nvidia_cosmos`
- `uv run python -m cli.instagram_html <reel-url> [--out raw.json] [--no-download]`
- `uv run python -m cli.instagram_graphql <reel-url> [--out raw.json] [--no-download]`
- `uv run python -m cli.threads <post-url-or-shortcode> [--out raw.json] [--no-download]`
- `uv run python -m cli.link_scraper <instagram-or-threads-url> [--out post.json]`
- `uv run python -m cli.youtube <video-url-or-id> [--out raw.json] [--no-download]`
- `uv run python -m cli.recipe_bench prepare` → `download-models` → `run [--pipelines ...]`
- `uv run python -m cli.recipe_parser <reel-url | video.mp4> [--pipeline ...] [--force-av]`
- `make cli <instagram|instagram_graphql|threads|link|youtube> "<url>" [args="..."]` is the root `Makefile` shortcut for the five scraper scripts above (`instagram` → `cli.instagram_html`); a new scraper script needs a `CLI_MODULE_<platform>` line there

## Child DOX Index
