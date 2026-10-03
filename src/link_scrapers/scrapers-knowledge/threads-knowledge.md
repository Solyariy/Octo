# Threads scraping knowledge

Findings behind `src/link_scrapers/threads.py`, verified live on 2026-10-03 (test post `https://www.threads.com/@_mister_nine_/post/DdO_YhfEXTX`, plus a browser HAR capture of the same post). Re-verify before relying on any of it: Meta changes these internals without notice.

## What does not work

- Plain-HTTP fetch of the permalink with a Chrome UA, or with curl's default `Accept: */*`, returns a 280–590 KB shell page: only Open Graph / `al:` meta tags, a `LSD` token, and an `X-IG-App-ID`. No post data.
- Facebook-crawler UA (`facebookexternalhit/1.1`) returns OG tags only: handle, a truncated text snippet, one 1200×628 preview image. No full media, counts or timestamp.
- The legacy GraphQL route from `github.com/m1guelpf/threads-re` (2023) is stale. `POST https://www.threads.com/api/graphql` with `doc_id=5587632691339264`, `variables={"postID": "<numeric id>"}`, `x-ig-app-id`, `x-fb-lsd` and the `lsd` field returns `{"data":{"data":null}}`. Other documented ids (profile `23996318473300828`, profile posts `6232751443445612`, replies `6307072669391286`, likers `9360915773983802`) were not re-tested.
- The post query's current `doc_id` could not be found: it is not in the first-load JS bundles, and the HAR's only GraphQL calls were `fetchBarcelonaExperimentQuery` (`doc_id=26349442214668312`) for experiment flags.
- Shortcode to numeric id (media pk) is plain base64 over the alphabet `A-Za-z0-9-_` (e.g. `DdO_YhfEXTX` → `3985401482421826775`); only relevant if a working GraphQL `doc_id` is found later.

## What works: permalink HTML with browser-like headers

- `GET https://www.threads.com/post/<shortcode>` (the `@handle` segment and `?xmt=…&slof=1` query are ignored) with:
  - `User-Agent`: a Safari UA (`Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15`)
  - `Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8`
- Result: about 1 MB of HTML containing the post. No cookies, CSRF token or login. `Accept-Language`, `Sec-Fetch-*` headers, `csrftoken`/`ig_did` cookies and the `xmt` query were tested and are not required.
- Tested matrix (same post): Safari UA + `Accept: */*` → shell; Safari UA + document `Accept` → full page (repeated several times); Chrome UA + document `Accept` → shell.
- The server is sensitive to the `Accept` header, not just the UA: keep both.

## Where the post lives in the HTML

- `<script type="application/json" data-sjs>` blocks (about 29 per page, a few KB to 200 KB each). The target post sits at `.../__bbox/result/data/media` inside the block that also holds the `BarcelonaPostPageTargetQueryRelayPreloader` data.
- Other blocks hold related posts (`BarcelonaLoggedOutRelatedPostsQuery…`, `…Upward…`, `…Downward…` preloaders) which also contain `thread_items` and posts with their own `code`. Match the dict by `code == <shortcode>` and a `caption` key, not by block position.
- Important fields of the post dict:
  - identity: `code`, `pk` (numeric id), `taken_at` (unix seconds), `user.username`, `user.pk`
  - text: `caption.text` (can be null for non-caption posts; `text_post_app_info.text_fragments.fragments[].plaintext` is the fallback)
  - counts: `like_count`; in `text_post_app_info`: `direct_reply_count`, `repost_count`, `quote_count`, `reshare_count` (strings)
  - media: `media_type` (1 image, 2 video, 8 carousel), `image_versions2.candidates[]` (several sizes, not strictly ordered: pick max `width`), `video_versions[]` (each `type`, `url`, `width`, `height`), `carousel_media[]` (each child has its own `image_versions2` / `video_versions`), `original_width` / `original_height`, `audio`
  - other: `text_post_app_info.link_preview_attachment`, `share_info` (quoted posts), `reply_control`, `pinned_post_info`
- The test post is `media_type` 8 with three images (571×550, 450×496, 550×562), caption "Коробка виявилась трошки замалою для нього", 16463 likes, 136 replies, 77 reposts.

## Share links

- `https://www.threads.com/share/<id>` answers `302` with `Location: https://www.threads.com/@<user>/post/<shortcode>?xmt=…&slof=1`. Read the `Location` with redirects disabled and extract the shortcode from it; the share page itself, if followed with the browser headers, also yields the full post (canonical and `barcelona://media?shortcode=` meta tags carry the shortcode).
- Example: `/share/BASG0l7Zsm` → post `DeB-dWdk93P` by `@andrii.mart`.

## Media files

- CDN hosts are `scontent-*.cdninstagram.com` / `scontent-*.xx.fbcdn.net`. Plain unauthenticated GETs work, but URLs carry an `oe=` expiry and signature, so download right after fetching.
- Downloaded JPEGs from the test post were valid, full-size files (`file` reported 571×550, 450×496, 550×562).

## Constants

- `X-IG-App-ID: 238260118697367` (Threads web; Instagram web uses `936619743392459`). Not needed for the HTML route.
- Page-level LSD token appears as `"LSD",[],{"token":"…"}`; not needed for the HTML route.
- URLs seen: both `threads.com` and `threads.net` host names are in circulation; the scraper accepts both.

## Limits and risks

- Rate limiting in code: 1 request per 5 s and 120 per hour (self-imposed, not a measured Threads limit). Tens of requests from one IP in a short test session did not trigger blocking.
- Not scraped: replies, thread continuations (`thread_items`), profile pages, likers.
- Private, deleted or login-walled posts return no `code`-matching dict, so `ThreadsFetchError` is raised with a hint that the shell page may have been served.
- Video posts have not been tested: the video path (`video_versions`, largest by width) follows the field layout seen in the HAR (26 `video_versions` mentions, mostly in related posts) but is unverified end-to-end.
