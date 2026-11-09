# src/link_scrapers DOX

## Purpose

- Resolve a submitted social-media URL (Instagram reels/posts, Threads posts, YouTube videos) to its metadata and a fetchable video URL, without logging in or using official APIs
- YouTube is scraper-only for now: `scrapers/youtube.py` is not wired into `LinkScraper`, `ScrapedPost` or `Platform`

## Ownership

- `scrapers/instagram_graphql.py` — async `fetch_reel` / `fetch_reel_json` / `parse_reel_data`, the `ReelData` dataclass, `InstagramFetchError`, and `extract_shortcode`. Scrapes Instagram's public GraphQL `doc_id` endpoint: pulls a `csrftoken` cookie from a plain GET to instagram.com and replays it with the web client's `x-ig-app-id` and `doc_id`
- `scrapers/threads.py` — async `fetch_post` / `fetch_post_html` / `extract_post_json` / `parse_post` / `download_media`, the `ThreadsPost` and `MediaItem` dataclasses, `ThreadsFetchError`, `extract_shortcode`, `resolve_shortcode` (also follows `threads.com/share/<id>` links via their 302 `Location`, behind the same limiters). Scrapes the permalink HTML (`threads.com/post/<shortcode>`) for the embedded post JSON; no GraphQL, cookies or tokens (details in `scrapers-knowledge/threads-knowledge.md`)
- `scrapers/youtube.py` — async `fetch_video` / `fetch_video_info` / `download_video`, sync `parse_video`, the `YouTubeVideo` dataclass, `YouTubeFetchError`, `extract_video_id`. Wraps yt-dlp: title, description, channel, counts and the selected format's direct URL (details in `scrapers-knowledge/youtube-knowledge.md`)
- `settings.py` — `InstagramSettings` / `instagram_settings` (endpoint URL, `IG_APP_ID`, `DOC_ID`, user agent, timeout, two `aiolimiter` limiters, `MAX_ATTEMPTS`, `SHORTCODE_RE`), `ThreadsSettings` / `threads_settings` (Safari user agent, document `Accept`, timeout, limiters, `MAX_ATTEMPTS`, `SHORTCODE_RE`, `SHARE_RE`) and `YouTubeSettings` / `youtube_settings` (`FORMAT`, `MERGE_OUTPUT_FORMAT`, `JS_RUNTIMES`, `SOCKET_TIMEOUT`, `RETRIES`, limiters, `VIDEO_ID_RE`)
- `scrapers-knowledge/` — detailed per-platform scraping notes, one file per platform (`threads-knowledge.md`, `instagram-knowledge.md`, `youtube-knowledge.md`): what was tried, what works, request/response shapes, field layouts, constants, limits. Prose reference only, no code
- `manager.py` — `LinkScraper`, the single entry point over `scrapers/`: `classify_platform` maps a URL to `Platform` (reusing each platform's `SHORTCODE_RE`/`SHARE_RE`) or raises `UnsupportedLinkError`; `scrap(url)` dispatches to `scrap_instagram_reel` / `scrap_threads_post` (which log and re-raise the platform's fetch error and return the raw scraper dataclass) and returns a normalized `ScrapedPost`. New platforms get a `Platform` member, a `scrap_<platform>_*` method, a `scrap` branch and a `Post._from_<platform>_*` converter
- `schemas.py` — `ScrapedPost`, the platform-neutral scrape result: image/video URL lists, empty `*_local_paths` lists for downloaders to fill, `text` and `Platform`. `Post.from_scraper` dispatches on `ReelData` / `ThreadsPost`; an Instagram thumbnail counts as an image only when there is no video

## Local Contracts

- Functions take an `aiohttp.ClientSession` from the caller and never create or close one, matching `src.utils.basic`. Exception: YouTube functions take no session, because yt-dlp owns its HTTP stack
- yt-dlp is blocking: every YouTube call runs in `asyncio.to_thread` behind `youtube_settings.SECONDS_LIMITER` (1 per 2 s) and `HOUR_LIMITER` (120 per hour). Retries are yt-dlp's own (`retries`, `extractor_retries`), not tenacity. yt-dlp errors become `YouTubeFetchError`, and its output goes through `src.utils.logs`, never stdout
- YouTube selects ≤480p avc1 video plus m4a audio, merged into one mp4 (`MERGE_OUTPUT_FORMAT`) by the imageio-ffmpeg binary passed as `ffmpeg_location` (there is no system ffmpeg). JS challenges are solved with the first runtime in `JS_RUNTIMES` (deno, then node) and the `yt-dlp-ejs` scripts; keep the `yt-dlp[default]` extra in `pyproject.toml`, which pins them. Live, upcoming and just-ended streams raise `YouTubeFetchError`. `download_video` reuses the fetched info and re-extracts once if its IP-bound format URLs went stale
- Every Instagram GraphQL POST passes through both `SECONDS_LIMITER` (1 per 10 s) and `HOUR_LIMITER` (60 per hour); keep new Instagram calls behind them
- `fetch_reel_json` retries only `aiohttp.ClientError`, up to `MAX_ATTEMPTS`, with exponential backoff, logging through the `src.utils.tenacity_logs` hooks. `InstagramFetchError` (429, 404, missing cookie, empty items) is never retried
- `IG_APP_ID` and `DOC_ID` are public constants scraped from Instagram's web client, not secrets. If Instagram rotates them the endpoint starts returning 400 and both need re-extracting from a fresh page load
- No credentials live here; the scrape is unauthenticated
- Threads only embeds the post JSON for browser-like navigations: keep the Safari `user-agent` and document `accept` header in `fetch_post_html`. Otherwise it serves a shell page and `extract_post_json` raises `ThreadsFetchError`. Every Threads GET passes through its own `SECONDS_LIMITER` (1 per 5 s) and `HOUR_LIMITER` (120 per hour); retries mirror the Instagram rule
- `fetch_post` returns text, author, counts and `MediaItem`s (carousel children, else the single largest video/image); it never downloads. `download_media(post, directory, session)` saves `NN.<ext>` files and sets `local_path`. CDN URLs expire, so download right after fetching. Replies and thread continuations are not scraped
- Detailed platform-specific information (endpoints, headers, request/response structure, field layouts, constants, failed approaches, test findings) goes into the matching file in `scrapers-knowledge/` (create `<platform>-knowledge.md` for a new platform), not into this file or code comments. Keep only the short operating rules here and update the knowledge file whenever a scraper's behavior or a verified finding changes
- Consumers: `src.api.schemas.InputPost` validates urls with `classify_platform`, and `src.services.omni_pipeline.OmniPipeline` scrapes with `scrap_bulk`. `scrap_bulk` returns exceptions in place, so callers own per-url error handling

## Work Guidance

- Settings classes need annotated fields and `arbitrary_types_allowed` (limiters, `ClientTimeout`, compiled patterns)

## Verification

- `uv run python -m cli.instagram_graphql <reel-url>`, `uv run python -m cli.threads <post-url>`, `uv run python -m cli.youtube <video-url>` and `uv run python -m cli.link_scraper <url>` for `LinkScraper` (flags in `cli/AGENTS.md`); no automated test suite
