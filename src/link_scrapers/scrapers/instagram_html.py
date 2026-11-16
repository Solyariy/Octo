"""Fetch an Instagram reel/post without logging in by parsing its server-rendered HTML.

The logged-out permalink page embeds the full post (`xig_polaris_media`) as Relay prefetch
JSON in `<script data-sjs>` blocks, the same packaging Threads uses, for browser-like
navigations. When it does not, the embed page (`/embed/captioned/`) is tried: its
`contextJSON` carries the legacy `shortcode_media` shape. No cookies, tokens or GraphQL calls.

CLI: `uv run python -m cli.instagram_html <reel-or-post-url> [--out raw.json] [--no-download]`
"""

import json
import re
from collections.abc import Iterator

import aiohttp
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.enums import Platform
from src.link_scrapers.errors import ScraperStatusError
from src.link_scrapers.scrapers.instagram_common import (
    InstagramFetchError,
    ReelData,
    extract_shortcode,
)
from src.link_scrapers.settings import instagram_settings
from src.utils.tenacity_logs import (
    tenacity_log_after,
    tenacity_log_before,
    tenacity_log_before_sleep,
)

SJS_SCRIPT_RE = re.compile(
    r'<script type="application/json"[^>]*data-sjs[^>]*>(.*?)</script>', re.S
)
CONTEXT_JSON_RE = re.compile(r'"contextJSON":("(?:[^"\\]|\\.)*")')
# Where Instagram sends anonymous visitors it has decided to block.
_BLOCK_PATH_PREFIXES = ("/accounts/login", "/challenge")


def _headers() -> dict[str, str]:
    return {
        "user-agent": instagram_settings.HTML_USER_AGENT,
        "accept": instagram_settings.HTML_ACCEPT,
        "accept-language": instagram_settings.ACCEPT_LANGUAGE,
    }


@retry(
    stop=stop_after_attempt(instagram_settings.MAX_ATTEMPTS),
    wait=wait_exponential(min=2, max=30),
    retry=retry_if_exception_type(aiohttp.ClientError),
    before=tenacity_log_before,
    before_sleep=tenacity_log_before_sleep,
    after=tenacity_log_after,
)
async def _get_html(
    url: str,
    shortcode: str,
    session: aiohttp.ClientSession,
) -> str:
    async with (
        instagram_settings.SECONDS_LIMITER,
        instagram_settings.HOUR_LIMITER,
        session.get(
            url,
            headers=_headers(),
            timeout=instagram_settings.HTML_REQUEST_TIMEOUT,
        ) as response,
    ):
        if response.status == 429:
            raise ScraperStatusError(Platform.INSTAGRAM, "rate limited (429)")
        if response.url.path.startswith(_BLOCK_PATH_PREFIXES):
            raise ScraperStatusError(
                Platform.INSTAGRAM,
                f"login wall (redirected to {response.url.path})",
            )
        if response.status == 404:
            raise InstagramFetchError(f"Post {shortcode!r} not found")
        response.raise_for_status()
        return await response.text()


async def fetch_permalink_html(shortcode: str, session: aiohttp.ClientSession) -> str:
    # `/p/<code>/` serves reels as well; the handle segment of shared urls is not needed.
    url = instagram_settings.PERMALINK_URL.format(shortcode=shortcode)
    return await _get_html(
        url,
        shortcode,
        session,
    )


async def fetch_embed_html(shortcode: str, session: aiohttp.ClientSession) -> str:
    url = instagram_settings.EMBED_URL.format(shortcode=shortcode)
    return await _get_html(
        url,
        shortcode,
        session,
    )


def _walk_media(node) -> Iterator[dict]:
    if isinstance(node, dict):
        media = node.get("xig_polaris_media")
        if isinstance(media, dict):
            yield media
        for value in node.values():
            yield from _walk_media(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_media(value)


def extract_permalink_media(html: str, shortcode: str) -> dict | None:
    """Return the post node (`if_not_gated_logged_out`) or None when the page lacks it.

    Raises `InstagramFetchError` for gated posts (age/sensitive-content walls), which the
    embed page would not unlock either.
    """
    for block in SJS_SCRIPT_RE.findall(html):
        if "xig_polaris_media" not in block or shortcode not in block:
            continue
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        for media in _walk_media(payload):
            if media.get("code") != shortcode:
                continue
            node = media.get("if_not_gated_logged_out")
            if media.get("gating_ruling") or not node:
                raise InstagramFetchError(
                    f"Post {shortcode!r} is gated for logged-out viewers: "
                    f"{media.get('gating_ruling')!r}"
                )
            return node
    return None


def extract_embed_media(html: str) -> dict | None:
    match = CONTEXT_JSON_RE.search(html)
    if not match:
        return None
    try:
        context = json.loads(json.loads(match.group(1)))
    except json.JSONDecodeError:
        return None
    return (context.get("gql_data") or {}).get("shortcode_media") or None


def _largest_image_url(candidates: list[dict]) -> str | None:
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.get("width") or 0)["url"]


def parse_permalink_media(shortcode: str, node: dict) -> ReelData:
    video_versions = node.get("video_versions") or []
    candidates = (node.get("image_versions2") or {}).get("candidates") or []
    return ReelData(
        shortcode=shortcode,
        caption=(node.get("caption") or {}).get("text"),
        like_count=node.get("like_count"),
        comment_count=node.get("comment_count"),
        # Variants carry no width/height here; entry 0 (type 101) is the progressive mp4.
        video_url=video_versions[0]["url"] if video_versions else None,
        thumbnail_url=_largest_image_url(candidates),
        username=(node.get("user") or {}).get("username"),
        raw=node,
        source="permalink",
    )


def parse_embed_media(shortcode: str, node: dict) -> ReelData:
    caption_edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
    return ReelData(
        shortcode=shortcode,
        caption=caption_edges[0]["node"].get("text") if caption_edges else None,
        like_count=(node.get("edge_liked_by") or {}).get("count"),
        comment_count=(node.get("edge_media_to_comment") or {}).get("count"),
        video_url=node.get("video_url"),
        thumbnail_url=node.get("display_url"),
        username=(node.get("owner") or {}).get("username"),
        raw=node,
        source="embed",
    )


async def fetch_reel(url_or_code: str, session: aiohttp.ClientSession) -> ReelData:
    """Permalink HTML first, embed page as fallback. Never downloads (see `download_reel`)."""
    shortcode = extract_shortcode(url_or_code)
    node = extract_permalink_media(
        await fetch_permalink_html(shortcode, session),
        shortcode,
    )
    if node:
        return parse_permalink_media(shortcode, node)
    node = extract_embed_media(await fetch_embed_html(shortcode, session))
    if node:
        return parse_embed_media(shortcode, node)
    raise InstagramFetchError(
        f"No post data for {shortcode!r} in the permalink or embed page: the post is "
        "private/removed, or Instagram changed the page layout"
    )
