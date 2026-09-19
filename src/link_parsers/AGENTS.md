# src/link_parsers DOX

## Purpose

- Resolve a submitted social-media URL (currently Instagram only) down to fetchable media: direct file URLs, or a downloaded video file, without going through the official Graph API

## Ownership

- `instagram.py` — `resolve`/`fetch`: yt-dlp first, falling back to `resolve_gallery_dl` (gallery-dl `--dump-json`) when yt-dlp raises `DownloadError`. No login; both tools accept an optional Netscape `cookiefile` for age/login-gated posts
- `instagram_graphql.py` — async `fetch_reel`/`fetch_reel_json`: unauthenticated scrape of Instagram's public GraphQL `doc_id` endpoint (technique: pull a `csrftoken` cookie from a plain GET to instagram.com, replay it with the fixed `x-ig-app-id`/`doc_id` web-client constants). Takes an `aiohttp.ClientSession` supplied by the caller — never created or closed internally, matching `utils/basic.py`'s convention. Returns caption, like/comment counts, video URL, thumbnail, username
- `instaloader_download.py` — CLI that downloads a reel's video file via an authenticated `instaloader` session (saved session file, exported browser cookies, or username/password login, in that preference order)

## Local Contracts

- These are standalone scripts, not FastAPI-integrated: `print` is used freely (not routed through `src.utils.logs`), matching each file's own `__main__`/CLI block
- No module here holds credentials; auth material (`cookiefile`, `session-file`, `IG_USERNAME`/`IG_PASSWORD`) is passed in by the caller or read from env, never hardcoded
- `instagram_graphql.py`'s `IG_APP_ID`/`DOC_ID` are public constants scraped from Instagram's own web client, not secrets; if Instagram changes them the endpoint starts 400ing and both need re-extracting from a fresh page load
- Nothing here is wired into `src.api` yet; all three are called manually or via their `__main__` block

## Work Guidance

- No standards decided yet beyond what's in Local Contracts

## Verification

- Run each module directly, e.g. `uv run python -m src.link_parsers.instagram_graphql <reel-url>`; no automated test suite

## Child DOX Index

- none
