# src/link_parsers DOX

## Purpose

- Resolve a submitted social-media URL (currently Instagram reels/posts only) to its metadata and a fetchable video URL, without logging in or using the official Graph API

## Ownership

- `instagram_graphql.py` — async `fetch_reel` / `fetch_reel_json` / `parse_reel_data`, the `ReelData` dataclass, `InstagramFetchError`, `extract_shortcode`, and a CLI `main()`. Scrapes Instagram's public GraphQL `doc_id` endpoint: pulls a `csrftoken` cookie from a plain GET to instagram.com and replays it with the web client's `x-ig-app-id` and `doc_id`
- `settings.py` — `InstagramSettings` / `instagram_settings`: endpoint URL, `IG_APP_ID`, `DOC_ID`, user agent, request timeout, the two `aiolimiter` rate limiters, `MAX_ATTEMPTS`, `SHORTCODE_RE`
- `manager.py` — `LinkDownloader`, a `LoggerMixin` stub whose `load_ig_reels` is not implemented yet

## Local Contracts

- Functions take an `aiohttp.ClientSession` from the caller and never create or close one, matching `src.utils.basic`; only the CLI `main()` opens its own session
- Every GraphQL POST passes through both `SECONDS_LIMITER` (1 per 10 s) and `HOUR_LIMITER` (60 per hour); keep new Instagram calls behind them
- `fetch_reel_json` retries only `aiohttp.ClientError`, up to `MAX_ATTEMPTS`, with exponential backoff, logging through the `src.utils.tenacity_logs` hooks. `InstagramFetchError` (429, 404, missing cookie, empty items) is never retried
- `IG_APP_ID` and `DOC_ID` are public constants scraped from Instagram's web client, not secrets. If Instagram rotates them the endpoint starts returning 400 and both need re-extracting from a fresh page load
- No credentials live here; the scrape is unauthenticated
- Library code logs through `src.utils.logs`; `print` is used only in the CLI `main()`
- Nothing here is wired into `src.api` yet

## Work Guidance

- `settings.py` currently fails at import: `InstagramSettings` fields have no type annotations, which pydantic rejects (`model-field-missing-annotation`). Annotate them, or mark them `ClassVar`, before using this package
- The CLI writes the downloaded video to `main_settings.INSTAGRAM_TEMP_DIR_PATH / "test.mp4"` and does not create that directory

## Verification

- `uv run python -m src.link_parsers.instagram_graphql <reel-url> [--out raw.json]`; no automated test suite
