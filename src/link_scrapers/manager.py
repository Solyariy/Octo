import asyncio

import aiohttp

from src.enums import Platform
from src.link_scrapers.schemas import Post
from src.link_scrapers.scrapers import instagram_graphql, threads
from src.link_scrapers.scrapers.instagram_graphql import InstagramFetchError, ReelData
from src.link_scrapers.scrapers.threads import ThreadsFetchError, ThreadsPost
from src.link_scrapers.settings import instagram_settings, threads_settings
from src.utils.logs import LoggerMixin


class UnsupportedLinkError(ValueError):
    pass


class LinkScraper(LoggerMixin):

    def __init__(self, aiohttp_client: aiohttp.ClientSession):
        self.aiohttp_client = aiohttp_client

    @staticmethod
    def classify_platform(url: str) -> Platform:
        if instagram_settings.SHORTCODE_RE.search(url):
            return Platform.INSTAGRAM
        if threads_settings.SHORTCODE_RE.search(url) or threads_settings.SHARE_RE.search(url):
            return Platform.THREADS
        raise UnsupportedLinkError(f"No scraper supports {url!r}")

    async def scrap(self, url: str) -> Post:
        """Dispatch `url` to the matching platform scraper and normalize the result."""
        platform = self.classify_platform(url)
        match platform:
            case Platform.INSTAGRAM:
                data = await self.scrap_instagram_reel(url)
            case Platform.THREADS:
                data = await self.scrap_threads_post(url)
        return Post.from_scraper(data)

    async def scrap_bulk(self, urls: list[str]) -> list[Post | Exception]:
        tasks = [self.scrap(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def scrap_instagram_reel(self, url: str) -> ReelData:
        try:
            reel = await instagram_graphql.fetch_reel(url, session=self.aiohttp_client)
        except InstagramFetchError as e:
            self.log_error("Instagram scrape failed", error=e, url=url)
            raise
        self.log_info("Scraped Instagram reel", shortcode=reel.shortcode, url=url)
        return reel

    async def scrap_threads_post(self, url: str) -> ThreadsPost:
        try:
            post = await threads.fetch_post(
                url, session=self.aiohttp_client
            )
        except ThreadsFetchError as e:
            self.log_error("Threads scrape failed", error=e, url=url)
            raise
        self.log_info(
            "Scraped Threads post", shortcode=post.shortcode, media=len(post.media), url=url
        )
        return post
