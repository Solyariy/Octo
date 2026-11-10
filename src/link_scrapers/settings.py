import re

import aiohttp
import aiolimiter
from pydantic_settings import BaseSettings, SettingsConfigDict


class InstagramSettings(BaseSettings):
    model_config = SettingsConfigDict(arbitrary_types_allowed=True)

    GRAPHQL_URL: str = "https://www.instagram.com/graphql/query"
    IG_APP_ID: str = "936619743392459"
    DOC_ID: str = "24368985919464652"
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    REQUEST_TIMEOUT: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=10)
    SECONDS_LIMITER: aiolimiter.AsyncLimiter = aiolimiter.AsyncLimiter(1, 60)
    HOUR_LIMITER: aiolimiter.AsyncLimiter = aiolimiter.AsyncLimiter(60, 3600)
    MAX_ATTEMPTS: int = 3
    SHORTCODE_RE: re.Pattern = re.compile(r"instagram\.com/(?:[^/]+/)?(?:reel|p|tv)/([^/?#]+)")


instagram_settings = InstagramSettings()


class ThreadsSettings(BaseSettings):
    model_config = SettingsConfigDict(arbitrary_types_allowed=True)

    # Threads only embeds the post JSON in the permalink HTML for browser-like navigations:
    # a Safari UA plus a document `Accept` header. curl's `*/*` or a Chrome UA gets a shell page.
    USER_AGENT: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.5 Safari/605.1.15"
    )
    ACCEPT: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ACCEPT_LANGUAGE: str = "en-US,en;q=0.9"
    REQUEST_TIMEOUT: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=20)
    SECONDS_LIMITER: aiolimiter.AsyncLimiter = aiolimiter.AsyncLimiter(1, 5)
    HOUR_LIMITER: aiolimiter.AsyncLimiter = aiolimiter.AsyncLimiter(120, 3600)
    MAX_ATTEMPTS: int = 3
    SHORTCODE_RE: re.Pattern = re.compile(r"threads\.(?:com|net)/(?:@[^/]+/)?post/([A-Za-z0-9_-]+)")
    SHARE_RE: re.Pattern = re.compile(r"threads\.(?:com|net)/share/[A-Za-z0-9_-]+")


threads_settings = ThreadsSettings()


class YouTubeSettings(BaseSettings):
    model_config = SettingsConfigDict(arbitrary_types_allowed=True)

    # avc1 video + m4a audio merged into one mp4 by the imageio-ffmpeg binary; PyAV decodes it.
    FORMAT: str = (
        "bv*[height<=480][ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[height<=480][ext=mp4]"
        "/bv*[height<=480]+ba/b[height<=480]"
    )
    MERGE_OUTPUT_FORMAT: str = "mp4"
    # yt-dlp solves YouTube's JS challenges with the first runtime found on PATH; it only
    # enables deno by default, so node (Homebrew) is listed too. Solver scripts: `yt-dlp-ejs`.
    JS_RUNTIMES: dict[str, dict] = {"deno": {}, "node": {}}
    SOCKET_TIMEOUT: float = 20
    RETRIES: int = 3
    SECONDS_LIMITER: aiolimiter.AsyncLimiter = aiolimiter.AsyncLimiter(1, 2)
    HOUR_LIMITER: aiolimiter.AsyncLimiter = aiolimiter.AsyncLimiter(120, 3600)
    VIDEO_ID_RE: re.Pattern = re.compile(
        r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)"
        r"([A-Za-z0-9_-]{11})"
    )


youtube_settings = YouTubeSettings()
