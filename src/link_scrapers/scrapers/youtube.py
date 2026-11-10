"""Fetch a YouTube video (title, description, media) without an API key, through yt-dlp.

yt-dlp is synchronous and owns its HTTP stack, so every call runs in `asyncio.to_thread`
behind the module limiters and no `aiohttp.ClientSession` is involved. Retries are yt-dlp's
own (`retries`, `extractor_retries`). Merges, if a fallback format needs one, use the
imageio-ffmpeg binary because the host has no system ffmpeg.

CLI: `uv run python -m cli.youtube <video-url-or-id> [--out raw.json] [--no-download]`
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import imageio_ffmpeg
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from src.enums import Platform
from src.link_scrapers.errors import ScraperStatusError
from src.link_scrapers.settings import youtube_settings
from src.utils.logs import Logger

# Live, upcoming and just-ended streams have no downloadable file yet.
_UNDOWNLOADABLE_LIVE_STATUSES = {"is_live", "is_upcoming", "post_live"}
# yt-dlp error text meaning YouTube refuses this host, not one video.
_PLATFORM_BLOCK_MARKERS = ("Sign in to confirm you're not a bot", "HTTP Error 429")


class YouTubeFetchError(Exception):
    pass


@dataclass
class YouTubeVideo:
    video_id: str
    url: str
    title: str
    description: str
    channel: str | None
    upload_date: datetime | None
    duration: int | None
    view_count: int | None
    like_count: int | None
    thumbnail_url: str | None
    video_url: str | None
    width: int | None
    height: int | None
    local_path: Path | None = None
    raw: dict = field(default_factory=dict, repr=False)


def extract_video_id(url_or_id: str) -> str:
    match = youtube_settings.VIDEO_ID_RE.search(url_or_id)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id):
        return url_or_id
    raise ValueError(f"Could not extract a video id from {url_or_id!r}")


def _canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


class _YtDlpLogger:
    """Routes yt-dlp output into the project logger; with `quiet` set, info goes to `debug`."""

    def debug(self, msg: str):
        Logger.debug(msg.removeprefix("[debug] "), source="yt-dlp")

    def info(self, msg: str):
        Logger.debug(msg, source="yt-dlp")

    def warning(self, msg: str):
        Logger.warning(msg, source="yt-dlp")

    def error(self, msg: str):
        Logger.warning(msg, source="yt-dlp")


def _ydl_options(**overrides) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "format": youtube_settings.FORMAT,
        "merge_output_format": youtube_settings.MERGE_OUTPUT_FORMAT,
        "js_runtimes": youtube_settings.JS_RUNTIMES,
        "socket_timeout": youtube_settings.SOCKET_TIMEOUT,
        "retries": youtube_settings.RETRIES,
        "extractor_retries": youtube_settings.RETRIES,
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "logger": _YtDlpLogger(),
        **overrides,
    }


def _extract(url: str, *, download: bool, **overrides) -> dict:
    try:
        with YoutubeDL(_ydl_options(**overrides)) as ydl:
            return ydl.sanitize_info(ydl.extract_info(url, download=download))
    except (DownloadError, ExtractorError) as e:
        if any(marker in str(e) for marker in _PLATFORM_BLOCK_MARKERS):
            raise ScraperStatusError(Platform.YOUTUBE, str(e)) from e
        raise YouTubeFetchError(str(e)) from e


async def fetch_video_info(video_id: str) -> dict:
    async with youtube_settings.SECONDS_LIMITER, youtube_settings.HOUR_LIMITER:
        return await asyncio.to_thread(
            _extract,
            _canonical_url(video_id),
            download=False,
        )


def _selected_video_format(info: dict) -> dict:
    # A merged selection lists its parts in `requested_formats`; a single one sits at top level.
    for fmt in info.get("requested_formats") or []:
        if fmt.get("vcodec") not in (None, "none"):
            return fmt
    return info


def parse_video(info: dict) -> YouTubeVideo:
    video_id = info.get("id") or ""
    if info.get("live_status") in _UNDOWNLOADABLE_LIVE_STATUSES:
        raise YouTubeFetchError(f"Video {video_id!r} is a live stream ({info['live_status']})")
    upload_date = info.get("upload_date")
    fmt = _selected_video_format(info)
    return YouTubeVideo(
        video_id=video_id,
        url=_canonical_url(video_id),
        title=info.get("title") or "",
        description=info.get("description") or "",
        channel=info.get("channel") or info.get("uploader"),
        upload_date=(
            datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=UTC) if upload_date else None
        ),
        duration=info.get("duration"),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
        thumbnail_url=info.get("thumbnail"),
        video_url=fmt.get("url"),
        width=fmt.get("width"),
        height=fmt.get("height"),
        raw=info,
    )


def _download(video: YouTubeVideo, directory: Path) -> Path:
    overrides = {"outtmpl": str(directory / "%(id)s.%(ext)s")}
    try:
        # Reuse the fetched info so the watch page is not extracted a second time.
        with YoutubeDL(_ydl_options(**overrides)) as ydl:
            info = ydl.process_ie_result(dict(video.raw), download=True)
    except (DownloadError, ExtractorError) as e:
        # Format URLs are IP-bound and expire after hours; re-extract once if they went stale.
        Logger.warning(
            "Stored YouTube formats failed, re-extracting",
            error=e,
            url=video.url,
        )
        info = _extract(
            video.url,
            download=True,
            **overrides,
        )
    downloads = info.get("requested_downloads") or []
    if not downloads or not downloads[0].get("filepath"):
        raise YouTubeFetchError(f"yt-dlp reported no file for {video.video_id!r}")
    return Path(downloads[0]["filepath"])


async def download_video(video: YouTubeVideo, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    async with youtube_settings.SECONDS_LIMITER, youtube_settings.HOUR_LIMITER:
        video.local_path = await asyncio.to_thread(
            _download,
            video,
            directory,
        )
    Logger.info(
        "Saved YouTube video",
        path=str(video.local_path),
        video_id=video.video_id,
    )
    return video.local_path


async def fetch_video(url_or_id: str) -> YouTubeVideo:
    video_id = extract_video_id(url_or_id)
    info = await fetch_video_info(video_id)
    return parse_video(info)
