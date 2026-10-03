"""Fetch a Threads post through `src.link_scrapers.threads`, print it and download its media
to `THREADS_TEMP_DIR_PATH/<shortcode>`.

Run with:

    uv run python -m cli.threads <post-url> [--out raw.json] [--no-download]
"""

import argparse
import asyncio
import json

import aiohttp

from src.link_scrapers.threads import fetch_post, resolve_shortcode
from src.settings import main_settings


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Threads post URL, /share/ link or bare shortcode")
    parser.add_argument(
            "--out", type=str, default=None, help="Optional path to dump the raw post JSON"
    )
    parser.add_argument("--no-download", action="store_true", help="Skip downloading media")
    args = parser.parse_args()

    async with aiohttp.ClientSession() as session:
        shortcode = await resolve_shortcode(args.url, session)
        directory = None if args.no_download else main_settings.THREADS_TEMP_DIR_PATH / shortcode
        post = await fetch_post(args.url, session=session, download_dir=directory)

    print(
            f"@{post.username} ({post.taken_at}) likes={post.like_count} "
            f"replies={post.reply_count} reposts={post.repost_count}"
    )
    print(post.text)
    for item in post.media:
        print(f"- {item.kind} {item.width}x{item.height} {item.local_path or item.url}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(post.raw, f, indent=2, ensure_ascii=False)
        print(f"Saved raw post to {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
