"""Fetch an Instagram reel/post through `src.link_scrapers.instagram_graphql`, print it and
save the video to `INSTAGRAM_TEMP_DIR_PATH/test.mp4`.

Run with:

    uv run python -m cli.instagram_graphql <reel-or-post-url> [--out raw.json]
"""

import argparse
import asyncio
import json

import aiohttp

from src.link_scrapers.instagram_graphql import fetch_reel
from src.settings import main_settings


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Reel/post URL or bare shortcode")
    parser.add_argument(
            "--out", type=str, default=None, help="Optional path to dump the raw JSON response"
    )
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
    asyncio.run(main())
