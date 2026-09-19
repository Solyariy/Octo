"""Fetch Instagram reel/post metadata via the public (unauthenticated) GraphQL doc_id
endpoint, following the technique described in:
https://medium.com/@seotanvirbd/how-i-built-a-python-tool-that-extracts-instagram-reel-data-without-authentication-api-keys-or-0fcb35cba7b7

No login or API key is required: a short-lived `csrftoken` cookie is pulled from a plain
GET to instagram.com and replayed on the GraphQL POST alongside a fixed `x-ig-app-id` and
`doc_id`, both public constants embedded in Instagram's own web client.

Usage:
    uv run python -m src.link_parsers.instagram_graphql <reel-or-post-url>
"""

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp
from tenacity import retry, stop_after_attempt, retry_if_exception_type, wait_exponential

from src.link_parsers.settings import instagram_settings
from src.settings import main_settings
from src.utils.tenacity_logs import tenacity_log_before, tenacity_log_before_sleep, tenacity_log_after


class InstagramFetchError(Exception):
    pass


@dataclass
class ReelData:
    shortcode: str
    caption: str | None
    like_count: int | None
    comment_count: int | None
    video_url: str | None
    thumbnail_url: str | None
    username: str | None
    raw: dict


def extract_shortcode(url_or_code: str) -> str:
    match = instagram_settings.SHORTCODE_RE.search(url_or_code)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", url_or_code):
        return url_or_code
    raise ValueError(f"Could not extract a shortcode from {url_or_code!r}")


async def _csrf_token(session: aiohttp.ClientSession) -> str:
    async with session.get(
            "https://www.instagram.com/",
            headers={"user-agent": instagram_settings.USER_AGENT},
            timeout=instagram_settings.REQUEST_TIMEOUT
    ) as resp:
        resp.raise_for_status()
    cookies = session.cookie_jar.filter_cookies("https://www.instagram.com")
    token_cookie = cookies.get("csrftoken")
    if not token_cookie:
        raise InstagramFetchError("Instagram did not set a csrftoken cookie")
    return token_cookie.value


@retry(
    stop=stop_after_attempt(instagram_settings.MAX_ATTEMPTS),
    wait=wait_exponential(min=2, max=30),
    retry=retry_if_exception_type(aiohttp.ClientError),
    before=tenacity_log_before,
    before_sleep=tenacity_log_before_sleep,
    after=tenacity_log_after
)
async def fetch_reel_json(shortcode_or_url: str, session: aiohttp.ClientSession) -> dict:
    shortcode = extract_shortcode(shortcode_or_url)
    csrf_token = await _csrf_token(session)

    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": instagram_settings.USER_AGENT,
        "x-csrftoken": csrf_token,
        "x-ig-app-id": instagram_settings.IG_APP_ID,
    }
    variables = json.dumps({"shortcode": shortcode})
    payload = f"variables={quote(variables)}&doc_id={instagram_settings.DOC_ID}"

    async with (
        instagram_settings.SECONDS_LIMITER,
        instagram_settings.HOUR_LIMITER,
        session.post(
            instagram_settings.GRAPHQL_URL,
            headers=headers,
            data=payload,
            timeout=instagram_settings.REQUEST_TIMEOUT
        ) as response
    ):
        if response.status == 429:
            raise InstagramFetchError("Rate limited by Instagram; try again later")
        if response.status == 404:
            raise InstagramFetchError(f"Reel {shortcode!r} not found or private")
        response.raise_for_status()
        return await response.json()


def parse_reel_data(shortcode: str, payload: dict) -> ReelData:
    items = payload.get("data", {}).get("xdt_api__v1__media__shortcode__web_info", {}).get("items", [])
    if not items:
        raise InstagramFetchError(f"No media items in response for {shortcode!r}")
    item = items[0]

    caption = (item.get("caption") or {}).get("text")
    video_versions = item.get("video_versions") or []
    video_url = video_versions[0]["url"] if video_versions else None
    thumbnail_candidates = (item.get("image_versions2") or {}).get("candidates") or []
    thumbnail_url = thumbnail_candidates[0]["url"] if thumbnail_candidates else None

    return ReelData(
        shortcode=shortcode,
        caption=caption,
        like_count=item.get("like_count"),
        comment_count=item.get("comment_count"),
        video_url=video_url,
        thumbnail_url=thumbnail_url,
        username=(item.get("user") or {}).get("username"),
        raw=payload,
    )


async def fetch_reel(shortcode_or_url: str, session: aiohttp.ClientSession) -> ReelData:
    shortcode = extract_shortcode(shortcode_or_url)
    payload = await fetch_reel_json(shortcode_or_url, session=session)
    return parse_reel_data(shortcode, payload)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Reel/post URL or bare shortcode")
    parser.add_argument("--out", type=str, default=None, help="Optional path to dump the raw JSON response")
    args = parser.parse_args()

    async with aiohttp.ClientSession() as session:
        data = await fetch_reel(args.url, session=session)
        print(data)
        if data.video_url:
            async with session.get(data.video_url) as video_resp:
                video_resp.raise_for_status()
                raw = await video_resp.read()
            with open(main_settings.INSTAGRAM_TEMP_DIR_PATH / "test.mp4", "wb") as f:
                f.write(raw)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(data.raw, f, indent=2)
        print(f"Saved raw response to {args.out}")


if __name__ == "__main__":
    URL = "https://www.instagram.com/reel/Dc-MjbqjZIs/?stkn=ODNpdXRjend4bW4z"
    asyncio.run(main())
