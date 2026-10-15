"""Fetch a Threads post (text + media) without logging in.

The permalink HTML embeds the full post as Relay prefetch JSON in `<script data-sjs>` blocks,
but only when the request looks like a browser navigation (Safari user agent and a document
`Accept` header); otherwise Threads serves a shell page with Open Graph tags only. No cookies,
tokens or GraphQL calls are needed.

CLI: `uv run python -m cli.threads <post-url> [--out raw.json] [--no-download]`
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import aiohttp
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.link_scrapers.settings import threads_settings
from src.utils.basic import download_and_save_file
from src.utils.logs import Logger
from src.utils.tenacity_logs import (
        tenacity_log_after,
        tenacity_log_before,
        tenacity_log_before_sleep,
)

SJS_SCRIPT_RE = re.compile(
        r'<script type="application/json"[^>]*data-sjs[^>]*>(.*?)</script>', re.S
)


class ThreadsFetchError(Exception):
    pass


@dataclass
class MediaItem:
    kind: Literal["image", "video"]
    url: str
    width: int | None = None
    height: int | None = None
    local_path: Path | None = None


@dataclass
class ThreadsPost:
    shortcode: str
    url: str
    username: str | None
    text: str
    taken_at: datetime | None
    like_count: int | None
    reply_count: int | None
    repost_count: int | None
    media: list[MediaItem] = field(default_factory=list)
    raw: dict = field(default_factory=dict, repr=False)


def extract_shortcode(url_or_code: str) -> str:
    match = threads_settings.SHORTCODE_RE.search(url_or_code)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", url_or_code):
        return url_or_code
    raise ValueError(f"Could not extract a shortcode from {url_or_code!r}")


async def resolve_shortcode(url_or_code: str, session: aiohttp.ClientSession) -> str:
    """Like `extract_shortcode`, but also follows `threads.com/share/<id>` links, which 302 to the
    canonical `/@user/post/<shortcode>` URL."""
    if not threads_settings.SHARE_RE.search(url_or_code):
        return extract_shortcode(url_or_code)
    share_url = url_or_code if url_or_code.startswith("http") else f"https://{url_or_code}"
    async with (threads_settings.SECONDS_LIMITER, threads_settings.HOUR_LIMITER,
                session.get(share_url, headers=_headers(), allow_redirects=False,
                            timeout=threads_settings.REQUEST_TIMEOUT) as response):
        location = response.headers.get("location")
        if response.status not in (301, 302, 303, 307, 308) or not location:
            raise ThreadsFetchError(f"Share link {url_or_code!r} did not redirect to a post")
    return extract_shortcode(location)


def _headers() -> dict[str, str]:
    return {
            "user-agent": threads_settings.USER_AGENT,
            "accept": threads_settings.ACCEPT,
            "accept-language": threads_settings.ACCEPT_LANGUAGE,
    }


@retry(
        stop=stop_after_attempt(threads_settings.MAX_ATTEMPTS),
        wait=wait_exponential(min=2, max=30),
        retry=retry_if_exception_type(aiohttp.ClientError),
        before=tenacity_log_before,
        before_sleep=tenacity_log_before_sleep,
        after=tenacity_log_after
)
async def fetch_post_html(shortcode: str, session: aiohttp.ClientSession) -> str:
    # Threads resolves the permalink from the shortcode alone; the handle segment is ignored.
    url = f"https://www.threads.com/post/{shortcode}"
    async with (threads_settings.SECONDS_LIMITER, threads_settings.HOUR_LIMITER,
                session.get(url, headers=_headers(),
                            timeout=threads_settings.REQUEST_TIMEOUT) as response):
        if response.status == 429:
            raise ThreadsFetchError("Rate limited by Threads; try again later")
        if response.status == 404:
            raise ThreadsFetchError(f"Post {shortcode!r} not found")
        response.raise_for_status()
        return await response.text()


def _walk_posts(node, shortcode: str) -> Iterator[dict]:
    if isinstance(node, dict):
        if node.get("code") == shortcode and "caption" in node:
            yield node
        for value in node.values():
            yield from _walk_posts(value, shortcode)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_posts(value, shortcode)


def extract_post_json(html: str, shortcode: str) -> dict:
    for block in SJS_SCRIPT_RE.findall(html):
        if shortcode not in block:
            continue
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        post = next(_walk_posts(payload, shortcode), None)
        if post:
            return post
    raise ThreadsFetchError(
            f"No post data for {shortcode!r} in the page: the post is private/removed, or "
            "Threads served the shell page (browser-like headers may have stopped working)"
    )


def _best_media(item: dict) -> MediaItem | None:
    videos = item.get("video_versions") or []
    if videos:
        best = max(videos, key=lambda v: v.get("width") or 0)
        return MediaItem("video", best["url"], best.get("width"), best.get("height"))
    candidates = (item.get("image_versions2") or {}).get("candidates") or []
    if candidates:
        best = max(candidates, key=lambda c: c.get("width") or 0)
        return MediaItem("image", best["url"], best.get("width"), best.get("height"))
    return None


def _text(post: dict) -> str:
    caption = (post.get("caption") or {}).get("text")
    if caption:
        return caption
    fragments = ((post.get("text_post_app_info") or {}).get("text_fragments")
                 or {}).get("fragments") or []
    return "".join(f.get("plaintext") or "" for f in fragments)


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_post(shortcode: str, post: dict) -> ThreadsPost:
    items = post.get("carousel_media") or [post]
    media = [m for m in map(_best_media, items) if m]
    info = post.get("text_post_app_info") or {}
    taken_at = post.get("taken_at")
    return ThreadsPost(
            shortcode=shortcode,
            url=f"https://www.threads.com/post/{shortcode}",
            username=(post.get("user") or {}).get("username"),
            text=_text(post),
            taken_at=datetime.fromtimestamp(taken_at, tz=UTC) if taken_at else None,
            like_count=post.get("like_count"),
            reply_count=_int(info.get("direct_reply_count")),
            repost_count=_int(info.get("repost_count")),
            media=media,
            raw=post,
    )


async def download_media(post: ThreadsPost, directory: Path, session: aiohttp.ClientSession):
    directory.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(post.media, start=1):
        suffix = Path(urlparse(item.url).path
                      ).suffix or (".mp4" if item.kind == "video" else ".jpg")
        destination = directory / f"{index:02d}{suffix}"
        item.local_path = await download_and_save_file(item.url, destination, session)
        Logger.info("Saved Threads media", path=str(destination), kind=item.kind)


async def fetch_post(
        url_or_code: str,
        session: aiohttp.ClientSession,
        download_dir: Path | None = None
) -> ThreadsPost:
    shortcode = await resolve_shortcode(url_or_code, session)
    html = await fetch_post_html(shortcode, session=session)
    post = parse_post(shortcode, extract_post_json(html, shortcode))
    if download_dir is not None:
        await download_media(post, download_dir, session)
    return post
