# YouTube scraping knowledge

Findings behind `../scrapers/youtube.py`, verified live on 2026-10-21 with yt-dlp 2026.08.19 (test videos `jNQXAC9IVRw` "Me at the zoo" and `dQw4w9WgXcQ`). Re-verify after upgrading yt-dlp: YouTube changes player internals often.

## Approach

- yt-dlp (`YoutubeDL.extract_info`) is used instead of hand-parsing `ytInitialData` or the YouTube Data API. It needs no API key or login, returns title and description for a single video, and downloads the file
- Calls run in `asyncio.to_thread`. `extract_info(download=False)` makes about 3 requests (watch page, player API JSON, m3u8)
- `download_video` passes the stored info to `process_ie_result(info, download=True)`, which downloads without extracting again. This is the same mechanism as `--load-info-json`

## Formats

- `FORMAT = bv*[height<=480][ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[height<=480][ext=mp4]/bv*[height<=480]+ba/b[height<=480]`, `merge_output_format = "mp4"`
- YouTube serves ≤480p only as separate DASH video-only and audio-only streams (the progressive itag 18 is 360p). A bare `bv*` selection therefore saves a silent file
- Result for `G6GmFT4QSIQ`: `135+140-7`, which is 480p h264 plus aac. yt-dlp downloads `<id>.f135.mp4` and `<id>.f140-7.m4a`, merges them into `<id>.mp4` and deletes the parts. The merged file is about 4.1 MB, against 2.9 MB video-only. PyAV (`src.utils.video.sample_frames`) decodes it
- Merging uses the imageio-ffmpeg binary (`imageio_ffmpeg.get_ffmpeg_exe()`) passed as `ffmpeg_location`; the host has no system ffmpeg, and no ffprobe is needed. The merge works through both `extract_info(download=True)` and `process_ie_result`
- EmbeddingGemma 2 has its audio encoder disabled, so the audio track is kept for completeness, not for embedding

## Format URLs

- Direct `googlevideo.com/videoplayback` URLs carry `ip=<client ip>` and `expire=<unix ts>` (about 6 h ahead). They are bound to the extracting IP and time-limited, so download them from the same host soon after fetching
- Plain aiohttp GETs of these URLs are unreliable (403s and throttling); download through yt-dlp

## Info-dict fields used

- `id`, `title`, `description`, `channel` (fallback `uploader`), `upload_date` (`YYYYMMDD`), `duration` (s), `view_count`, `like_count`, `thumbnail`, `live_status`
- The selected format is the top-level `url`/`width`/`height` for a single format. For a merged selection it is the entry in `requested_formats` whose `vcodec` is not `none`
- After a download, `requested_downloads[0]["filepath"]` is the saved file
- `live_status` values `is_live`, `is_upcoming` and `post_live` are rejected. `not_live` and `was_live` download normally

## Known warnings and failures

- YouTube's player JS challenges (signature / `n` throttling) need a JS runtime plus the `yt-dlp-ejs` solver scripts. Without them yt-dlp warns "No supported JavaScript runtime could be found… some formats may be missing", and extraction falls back to the `visionos` client with a reduced format list
  - yt-dlp enables only `deno` by default. `JS_RUNTIMES = {"deno": {}, "node": {}}` also enables node, which exists on the dev host (Homebrew, v26); the log then shows `[jsc:node] Solving JS challenges using node`
  - `yt-dlp-ejs` comes from the `yt-dlp[default]` extra, which pins the matching version (0.8.0 for 2026.08.19). Keep the extra so upgrades stay in sync. `remote_components` (fetching solvers from npm/GitHub) stays disabled
  - The `python:3.13-slim` Docker image has no JS runtime, so containers still extract in degraded mode
- An unavailable id raises `DownloadError("ERROR: [youtube] <id>: This video is unavailable")`, which is surfaced as `YouTubeFetchError`
- Datacenter IPs can hit "Sign in to confirm you're not a bot"; that needs cookies (`cookiefile`), which are not configured
