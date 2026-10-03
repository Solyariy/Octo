# Instagram scraping knowledge

Findings behind `src/link_scrapers/instagram_graphql.py`, verified live on 2026-10-03 with the test reel `https://www.instagram.com/reel/Dc-MjbqjZIs/?stkn=ODNpdXRjend4bW4z` (public reel by `im_leoc`). The technique comes from the tutorial `https://medium.com/@seotanvirbd/how-i-built-a-python-tool-that-extracts-instagram-reel-data-without-authentication-api-keys-or-0fcb35cba7b7`. Only the happy path was tested; re-verify before relying on it: Meta rotates `doc_id`s and changes response shapes without notice.

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

- HTTP 429 → `InstagramFetchError("Rate limited…")`; 404 → "not found or private". Both are final, never retried. Other `aiohttp.ClientError`s (including `raise_for_status` on 400) are retried up to `MAX_ATTEMPTS` (3) with exponential backoff (2–30 s).
- A 400 is the expected symptom of a rotated `doc_id` or `x-ig-app-id`: re-extract them from a fresh Instagram web page load or network capture.
- Self-imposed rate limits, not measured Instagram limits: 1 request per 10 s and 60 per hour, applied to the GraphQL POST only (the `csrftoken` GET is not limited, so each reel costs one unlimited GET plus one limited POST).
- The `csrftoken` is fetched anew on every attempt; it is not cached across reels.

## Media files

- The CLI downloaded `video_url` with a plain GET, no auth: a valid ~2 MB MP4 (`file`: ISO Media) for the 10 s test reel. Instagram CDN URLs (`scontent-*.cdninstagram.com`) carry signed `oe=` expiry parameters, so download right after fetching.
- Image-only posts have no `video_versions`, so `video_url` is `None` and only `thumbnail_url` is set. Carousels are not expanded.

## Not covered / unverified

- Not scraped: comments, profile data, stories, carousel children, audio.
- Verified: `DOC_ID` `24368985919464652` and `x-ig-app-id` `936619743392459` are still accepted (HTTP 200 with items). Not verified: private accounts, deleted reels, age-gated reels, image posts, carousels, error paths (429/404/400).
- The `csrftoken` GET emits a `DeprecationWarning` (`filter_cookies` wants a `yarl.URL`, not a `str`); harmless today.
- Threads needed a different technique because its `doc_id` route stopped working (see `threads-knowledge.md`); Instagram may eventually follow, in which case the fallback is parsing the permalink HTML, as `threads.py` does.
