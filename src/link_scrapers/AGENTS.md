# src/link_scrapers DOX

## Purpose

- Resolve a submitted social-media URL (Instagram reels/posts and Threads posts) to its metadata and a fetchable video URL, without logging in or using the official Graph API

## Ownership

- `instagram_graphql.py` — async `fetch_reel` / `fetch_reel_json` / `parse_reel_data`, the `ReelData` dataclass, `InstagramFetchError`, and `extract_shortcode`. Scrapes Instagram's public GraphQL `doc_id` endpoint: pulls a `csrftoken` cookie from a plain GET to instagram.com and replays it with the web client's `x-ig-app-id` and `doc_id`
- `threads.py` — async `fetch_post` / `fetch_post_html` / `extract_post_json` / `parse_post` / `download_media`, the `ThreadsPost` and `MediaItem` dataclasses, `ThreadsFetchError`, `extract_shortcode`, `resolve_shortcode` (also follows `threads.com/share/<id>` links via their 302 `Location`, behind the same limiters). Scrapes the permalink HTML (`threads.com/post/<shortcode>`) for the embedded post JSON; no GraphQL, cookies or tokens (details in `scrapers-knowledge/threads-knowledge.md`)
- `settings.py` — `InstagramSettings` / `instagram_settings` (endpoint URL, `IG_APP_ID`, `DOC_ID`, user agent, timeout, two `aiolimiter` limiters, `MAX_ATTEMPTS`, `SHORTCODE_RE`) and `ThreadsSettings` / `threads_settings` (Safari user agent, document `Accept`, timeout, limiters, `MAX_ATTEMPTS`, `SHORTCODE_RE`, `SHARE_RE`)
- `scrapers-knowledge/` — detailed per-platform scraping notes, one file per platform (`threads-knowledge.md`, `instagram-knowledge.md`): what was tried, what works, request/response shapes, field layouts, constants, limits. Prose reference only, no code
- `manager.py` — `LinkDownloader`, a `LoggerMixin` stub whose `load_ig_reels` is not implemented yet

## Local Contracts

- Functions take an `aiohttp.ClientSession` from the caller and never create or close one, matching `src.utils.basic`
- Every Instagram GraphQL POST passes through both `SECONDS_LIMITER` (1 per 10 s) and `HOUR_LIMITER` (60 per hour); keep new Instagram calls behind them
- `fetch_reel_json` retries only `aiohttp.ClientError`, up to `MAX_ATTEMPTS`, with exponential backoff, logging through the `src.utils.tenacity_logs` hooks. `InstagramFetchError` (429, 404, missing cookie, empty items) is never retried
- `IG_APP_ID` and `DOC_ID` are public constants scraped from Instagram's web client, not secrets. If Instagram rotates them the endpoint starts returning 400 and both need re-extracting from a fresh page load
- No credentials live here; the scrape is unauthenticated
- Threads only embeds the post JSON for browser-like navigations: keep the Safari `user-agent` and document `accept` header in `fetch_post_html`. Otherwise it serves a shell page and `extract_post_json` raises `ThreadsFetchError`. Every Threads GET passes through its own `SECONDS_LIMITER` (1 per 5 s) and `HOUR_LIMITER` (120 per hour); retries mirror the Instagram rule
- `fetch_post` returns text, author, counts and `MediaItem`s (carousel children, else the single largest video/image); with `download_dir` it also saves `NN.<ext>` files there and sets `local_path`. CDN URLs expire, so download right after fetching. Replies and thread continuations are not scraped
- Detailed platform-specific information (endpoints, headers, request/response structure, field layouts, constants, failed approaches, test findings) goes into the matching file in `scrapers-knowledge/` (create `<platform>-knowledge.md` for a new platform), not into this file or code comments. Keep only the short operating rules here and update the knowledge file whenever a scraper's behavior or a verified finding changes
- Nothing here is wired into `src.api` yet

## Work Guidance

- Settings classes need annotated fields and `arbitrary_types_allowed` (limiters, `ClientTimeout`, compiled patterns)

## Verification

- `uv run python -m cli.instagram_graphql <reel-url>` and `uv run python -m cli.threads <post-url>` (flags in `cli/AGENTS.md`); no automated test suite
