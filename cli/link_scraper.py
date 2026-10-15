"""Scrape a post through `src.link_scrapers.manager.LinkScraper`, which classifies the url,
dispatches to the matching platform scraper and normalizes the result into a `Post`.

Run with:

    uv run python -m cli.link_scraper <post-url> [--out post.json]
"""

import argparse
import asyncio

import aiohttp

from src.link_scrapers.manager import LinkScraper, UnsupportedLinkError
from src.link_scrapers.scrapers.instagram_graphql import InstagramFetchError
from src.link_scrapers.scrapers.threads import ThreadsFetchError


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Instagram or Threads post URL")
    parser.add_argument(
            "--out", type=str, default=None, help="Optional path to dump the normalized Post JSON"
    )
    args = parser.parse_args()

    try:
        platform = LinkScraper.classify_platform(args.url)
    except UnsupportedLinkError as e:
        print(e)
        return 1
    print(f"Platform: {platform}")

    async with aiohttp.ClientSession() as session:
        try:
            post = await LinkScraper(session).scrap(args.url)
        except (InstagramFetchError, ThreadsFetchError) as e:
            print(f"Scrape failed: {e}")
            return 1

    print(post.model_dump_json(indent=2))

    if args.out:
        with open(args.out, "w") as f:
            f.write(post.model_dump_json(indent=2))
        print(f"Saved post to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
