import re

import aiohttp
import aiolimiter
from pydantic_settings import BaseSettings


class InstagramSettings(BaseSettings):
    GRAPHQL_URL = "https://www.instagram.com/graphql/query"
    IG_APP_ID = "936619743392459"
    DOC_ID = "24368985919464652"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)
    SECONDS_LIMITER = aiolimiter.AsyncLimiter(1, 10)
    HOUR_LIMITER = aiolimiter.AsyncLimiter(60, 3600)
    MAX_ATTEMPTS = 3
    SHORTCODE_RE = re.compile(r"instagram\.com/(?:[^/]+/)?(?:reel|p|tv)/([^/?#]+)")


instagram_settings = InstagramSettings()
