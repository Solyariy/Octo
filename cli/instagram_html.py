"""Fetch an Instagram reel/post through `src.link_scrapers.scrapers.instagram_html` (permalink
HTML, embed page as fallback), print it and save its video and description to
`INSTAGRAM_TEMP_DIR_PATH/<shortcode>/{video.mp4,caption.txt}`.

Run with:

    uv run python -m cli.instagram_html <reel-or-post-url> [--out raw.json] [--no-download]
"""

import argparse
import asyncio
import json

import aiohttp

from src.link_scrapers.errors import ScraperStatusError
from src.link_scrapers.scrapers.instagram_common import InstagramFetchError, download_reel
from src.link_scrapers.scrapers.instagram_html import fetch_reel
from src.settings import main_settings


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Reel/post URL or bare shortcode")
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional path to dump the raw post node JSON",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Skip saving the video and description",
    )
    args = parser.parse_args()

    async with aiohttp.ClientSession() as session:
        try:
            data = await fetch_reel(args.url, session=session)
        except (InstagramFetchError, ScraperStatusError) as exc:
            print(f"Instagram fetch failed: {exc}")
            return 1
        if not args.no_download:
            directory = main_settings.INSTAGRAM_TEMP_DIR_PATH / data.shortcode
            await download_reel(
                data,
                directory,
                session,
            )

    print(
        f"source={data.source} @{data.username} likes={data.like_count} comments={data.comment_count}"
    )
    print(data.caption or "<no description>")
    print(f"video: {data.video_local_path or data.video_url or '<no video>'}")
    print(f"thumbnail: {data.thumbnail_url or '<none>'}")
    if data.caption_local_path:
        print(f"description: {data.caption_local_path}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(
                data.raw,
                f,
                indent=2,
                ensure_ascii=False,
            )
        print(f"Saved raw post node to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
