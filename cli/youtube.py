"""Fetch a YouTube video through `src.link_scrapers.scrapers.youtube`, print its metadata and
download it to `YOUTUBE_TEMP_DIR_PATH/<id>.<ext>`.

Run with:

    uv run python -m cli.youtube <video-url-or-id> [--out raw.json] [--no-download]
"""

import argparse
import asyncio
import json

from src.link_scrapers.scrapers.youtube import YouTubeFetchError, download_video, fetch_video
from src.settings import main_settings


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="YouTube watch/shorts/youtu.be URL or bare video id")
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional path to dump the raw info JSON",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Skip downloading the video",
    )
    args = parser.parse_args()

    try:
        video = await fetch_video(args.url)
        if not args.no_download:
            await download_video(video, main_settings.YOUTUBE_TEMP_DIR_PATH)
    except YouTubeFetchError as e:
        print(f"Scrape failed: {e}")
        return 1

    print(
        f"{video.title!r} by {video.channel} ({video.upload_date}) "
        f"duration={video.duration}s views={video.view_count} likes={video.like_count}"
    )
    print(f"format: {video.width}x{video.height} {video.local_path or video.video_url}")
    print(video.description)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(
                video.raw,
                f,
                indent=2,
                ensure_ascii=False,
            )
        print(f"Saved raw info to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
