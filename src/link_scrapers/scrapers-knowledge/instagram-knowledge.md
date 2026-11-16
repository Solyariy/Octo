# Instagram scraping knowledge

The live scraper is `../scrapers/instagram_html.py` (see "Alternative routes" below). The GraphQL sections describe the standalone `../scrapers/instagram_graphql.py`.

Findings behind `../scrapers/instagram_graphql.py`, verified live on 2026-10-03 with the test reel `https://www.instagram.com/reel/Dc-MjbqjZIs/?stkn=ODNpdXRjend4bW4z` (public reel by `im_leoc`). The technique comes from the tutorial `https://medium.com/@seotanvirbd/how-i-built-a-python-tool-that-extracts-instagram-reel-data-without-authentication-api-keys-or-0fcb35cba7b7`. Only the happy path was tested; re-verify before relying on it: Meta rotates `doc_id`s and changes response shapes without notice.

## Approach

- Unauthenticated GraphQL "doc_id" query against Instagram's web endpoint. No login, API key or session cookie of a real account.
- Two requests per reel:
  1. `GET https://www.instagram.com/` with a desktop `User-Agent`. The response body is ignored; only the `csrftoken` cookie it sets is used (read from the aiohttp cookie jar). A missing cookie raises `InstagramFetchError`.
  2. `POST https://www.instagram.com/graphql/query` replaying that token.
- Request headers of the POST:
  - `content-type: application/x-www-form-urlencoded`
  - `user-agent`: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36`
  - `x-csrftoken`: the cookie value (the same session also sends the cookie itself)
  - `x-ig-app-id: 936619743392459` (Instagram web; Threads web uses `238260118697367`)
- Body: `variables=<url-quoted JSON {"shortcode": "<code>"}>&doc_id=24368985919464652`.
- `doc_id` and `x-ig-app-id` are public constants embedded in Instagram's own web client, not secrets. Both live in `InstagramSettings`.

## Response shape

- Reel data sits at `data.xdt_api__v1__media__shortcode__web_info.items[0]`. An empty `items` list raises `InstagramFetchError` (private, deleted or login-walled media, or a stale `doc_id`).
- Fields used by `parse_reel_data`:
  - `caption.text` (`caption` can be null)
  - `like_count`, `comment_count`
  - `user.username`
  - `video_versions[]` → `url` (the code takes element 0)
  - `image_versions2.candidates[]` → `url` (the code takes element 0 as the thumbnail)
- The full payload is kept on `ReelData.raw`; many more fields exist (`taken_at`, `play_count`, `carousel_media`, `media_type`, `owner`, …) and are not parsed.
- Test reel (`media_type` 2, `product_type` `clips`): response keys are `data`, `extensions`, `status`; `caption.text` "yes yes yes and yes!", 3,882,902 likes, 8,686 comments, `taken_at` 1788753410, `carousel_media` null. `play_count` is absent (`view_count` exists instead), as are duration fields at top level.
- `video_versions` held 3 entries (types 101/102/103), all 720×1280, so element 0 is a valid pick but they are quality/codec variants, not sizes. `image_versions2.candidates` held 11 entries: 640×1136 first, descending to 240×426, followed by square 640×640…150×150 crops. Element 0 happens to be the largest full-frame cover, but order is not guaranteed; pick by max `width`/`height` if it matters (the Threads route showed unordered candidates).
- Other useful top-level keys present: `code`, `pk`, `id`, `media_type`, `product_type`, `taken_at`, `view_count`, `has_audio`, `original_width`/`original_height`, `video_dash_manifest`, `owner`, `user` (`username`, `pk`, `is_private`), `clips_metadata`, `carousel_media_count`.

## URL handling

- `SHORTCODE_RE` matches `instagram.com/[<user>/](reel|p|tv)/<code>`; query strings such as `?stkn=…` are dropped. A bare shortcode (`[A-Za-z0-9_-]+`) is also accepted. Stories, profile URLs and `/share/` links are not handled.

## Errors and limits

- HTTP 429 → `ScraperStatusError(INSTAGRAM, "rate limited (429)")`; 401 → `ScraperStatusError(INSTAGRAM, "blocked (401): <message>")`; 404 → `InstagramFetchError("not found or private")`. All three are final, never retried; the first two make `LinkScraper.scrap_bulk` abort the rest of the batch's Instagram urls.
- 401 seen live on 2026-11-10 after ~30 GraphQL POSTs from one IP within a few minutes (10 reels × 3 retries): body `{"message":"Please wait a few minutes before you try again.","require_login":true,"igweb_rollout":true,"status":"fail"}`. The `csrftoken` GET still returns 200. It is an IP-level anonymous-access throttle, not a stale `doc_id` (that gives 400); retrying extends it, so wait it out. Other `aiohttp.ClientError`s (including `raise_for_status` on 400) are retried up to `MAX_ATTEMPTS` (3) with exponential backoff (2–30 s).
- A 400 is the expected symptom of a rotated `doc_id` or `x-ig-app-id`: re-extract them from a fresh Instagram web page load or network capture.
- Self-imposed rate limits, not measured Instagram limits: 1 request per 60 s and 60 per hour (`instagram_settings` limiters, shared with the HTML scraper), applied to the GraphQL POST only (the `csrftoken` GET is not limited, so each reel costs one unlimited GET plus one limited POST).
- The `csrftoken` is fetched anew on every attempt; it is not cached across reels.

## Media files

- `download_reel` saves `video.mp4` plus the caption text as `caption.txt` (UTF-8) per shortcode directory; the caption comes from the same GraphQL payload, no extra request.
- The CLI downloaded `video_url` with a plain GET, no auth: a valid ~2 MB MP4 (`file`: ISO Media) for the 10 s test reel. Instagram CDN URLs (`scontent-*.cdninstagram.com`) carry signed `oe=` expiry parameters, so download right after fetching.
- Image-only posts have no `video_versions`, so `video_url` is `None` and only `thumbnail_url` is set. Carousels are not expanded.

## Not covered / unverified

- Not scraped: comments, profile data, stories, carousel children, audio.
- Verified: `DOC_ID` `24368985919464652` and `x-ig-app-id` `936619743392459` are still accepted (HTTP 200 with items). Not verified: private accounts, deleted reels, age-gated reels, image posts, carousels, error paths (429/404/400).
- The `csrftoken` GET emits a `DeprecationWarning` (`filter_cookies` wants a `yarl.URL`, not a `str`); harmless today.
- Threads needed a different technique because its `doc_id` route stopped working (see `threads-knowledge.md`); Instagram may eventually follow, in which case the fallback is parsing the permalink HTML, as `threads.py` does.

## Alternative routes (verified 2026-11-16)

These findings back `../scrapers/instagram_html.py`: permalink first, embed page as fallback, both behind the shared limiters. It uses `/p/<code>/` for reels too, and that was verified to serve reels. Context: from this dev IP the GraphQL route above returned 401 `"Please wait a few minutes before you try again."` (`require_login`) on the first POST of the day, so the current scraper fails. `ahmedrangel/instagram-media-scraper`'s `/api/graphql` variant (`doc_id` `10015901848480474`, hardcoded `lsd` `AVqbxe3J_YA`, `X-ASBD-ID 129477`) returned HTTP 200 with body `{"errors":[{"message":"Rate limit exceeded","code":1675004}]}`. That variant reports throttling as a 200, not a 429. While both GraphQL routes were blocked, the HTML routes below still worked from the same IP. Tested with 5 seed reels and 1 image post, one request each, 3 s apart.

- **Permalink HTML (best candidate).** `GET https://www.instagram.com/reel/<code>/` (also `/p/<code>/`) with the Threads-style Safari `user-agent`, document `accept` and `accept-language: en-US,en;q=0.9`; no cookies or tokens. 200, ~640 KB. The logged-out SSR page embeds the full post in a `["RelayPrefetchedStreamCache","next",[],["adp_PolarisLoggedOutDesktopWWWPostRootContentQueryRelayPreloader_<hash>",{"__bbox":{"result":{"data":{"xig_polaris_media":{…}}}}}]]` script entry. To extract it, find that marker and read the balanced JSON object after it. Do not regex-match `"items":[`. That key is absent, and there is no `xdt_api__v1__…` key either.
  - `xig_polaris_media`: `pk`, `code`, `gating_ruling` (null when public), `comments_connection`, `if_not_gated_logged_out`.
  - `if_not_gated_logged_out` holds the v1-style media node: `caption.text`, `user.username`, `like_count`, `comment_count`, `taken_at`, `media_type` (2 video / 1 image), `product_type` (`clips` / `feed`), `video_versions[]` (3 entries, types 101/102/103, no width/height), `image_versions2`, `video_dash_manifest`, `original_width/height`, `has_audio`, `location`, `usertags`. `video_duration` is absent.
  - 5/5 posts parsed (4 reels with English/Ukrainian captions, 1 image post with 0 `video_versions`). `video_versions[0].url` downloaded with a plain GET as a valid 6 MB MP4. Carousels were not tested; `carousel_media` is expected on the same node.
- **Embed page.** `GET https://www.instagram.com/reel/<code>/embed/captioned/`, same headers. 200, ~240 KB. `"contextJSON":"<JSON string>"` holds `gql_data.shortcode_media` in the legacy GraphQL shape: `__typename` (`GraphVideo`), `video_url`, `video_duration`, `display_url`, `edge_media_to_caption.edges[0].node.text`, `owner.username`, `edge_sidecar_to_children`. Worked for 4/4 reels. For the image post `gql_data` was absent, so the post has to come from the permalink. This route is a good fallback and is the only one that returns `video_duration`.
- **yt-dlp (`2026.08.19`, already a dependency).** `extract_info("https://www.instagram.com/reel/<code>/")` worked anonymously: description = caption, 13 formats including DASH. `title` is generic (`Video by <user>`) and `duration` is None. It needs an ffmpeg for merged formats, as in `youtube.py`. yt-dlp's own extractor breaks under the same anonymous throttling; its usual fix is `--cookies`.
- **Headless browser (Playwright 1.55, local Chrome, `channel="chrome"`, headless).** Navigation 200 in ~5.6 s with no login wall. The page HTML contains the same `video_versions` JSON. The `<video>` src is a `blob:` (MSE) URL, so the browser gives no direct video URL, and the only `/api/graphql` XHRs were small (<250 B) non-media calls. A browser therefore adds nothing over the plain permalink GET, at ~100× the cost. Keep it only as a last resort if Instagram starts requiring JS-executed checks.
- **Not used.** The `?__a=1&__d=dis` route and `i.instagram.com/api/v1/media/<pk>/info/` both need a logged-in `sessionid`, which breaks the unauthenticated rule. Commercial APIs (Apify actors and similar) cost money and add a third party.
- **Comments (not scraped).** `xig_polaris_media.comments_connection.edges` holds only the ~10–12 newest top-level comments, newest first. `page_info.has_next_page` is true for busy posts. None of the 5 samples included an author comment, and `is_pinned` is null for logged-out viewers. The embed page gives only `edge_media_to_comment.count`. `GET /api/v1/media/<pk>/comments/` with `x-ig-app-id` answers 302 (login) anonymously. A post's first or pinned comment (often the author's recipe) is therefore unreachable without login.
- **Unknown.** The HTML routes' own rate limit was not measured, and a burst was deliberately not tried so the dev IP would not get blocked. Datacenter IPs are reported to be blocked faster than residential ones.
