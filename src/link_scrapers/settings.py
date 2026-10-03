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
    SECONDS_LIMITER: aiolimiter.AsyncLimiter = aiolimiter.AsyncLimiter(1, 10)
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
