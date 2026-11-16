"""Pieces shared by the Instagram scrapers (`instagram_html`, `instagram_graphql`): the result
dataclass, the per-post error, shortcode parsing and the downloader."""

import re
from dataclasses import dataclass
from pathlib import Path

import aiohttp

from src.link_scrapers.settings import instagram_settings
from src.utils.basic import download_and_save_file


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
    source: str | None = None
    video_local_path: Path | None = None
    caption_local_path: Path | None = None


def extract_shortcode(url_or_code: str) -> str:
    match = instagram_settings.SHORTCODE_RE.search(url_or_code)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", url_or_code):
        return url_or_code
    raise ValueError(f"Could not extract a shortcode from {url_or_code!r}")


async def download_reel(
    data: ReelData,
    directory: Path,
    session: aiohttp.ClientSession,
) -> ReelData:
    """Save the caption to `caption.txt` and, when present, the video to `video.mp4` in
    `directory` (created), setting the `*_local_path` fields. CDN URLs expire, so call this
    right after fetching."""
    directory.mkdir(parents=True, exist_ok=True)
    data.caption_local_path = directory / "caption.txt"
    data.caption_local_path.write_text(data.caption or "", encoding="utf-8")
    if data.video_url:
        data.video_local_path = await download_and_save_file(
            data.video_url,
            directory / "video.mp4",
            session,
        )
    return data
