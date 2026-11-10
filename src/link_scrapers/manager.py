import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

import aiohttp

from src.enums import Platform, ProcessingStatus
from src.link_scrapers.errors import ScraperStatusError
from src.link_scrapers.schemas import ScrapedPost
from src.link_scrapers.scrapers import instagram_graphql, threads
from src.link_scrapers.scrapers.instagram_graphql import InstagramFetchError, ReelData
from src.link_scrapers.scrapers.threads import ThreadsFetchError, ThreadsPost
from src.link_scrapers.settings import instagram_settings, threads_settings
from src.utils.logs import LoggerMixin

if TYPE_CHECKING:
    # Runtime import would cycle: postgres.manager -> api.schemas -> this module.
    from src.db.postgres.manager import PostgresManager

# The platform answered, so the request itself got through; the post is the problem.
_POST_LEVEL_ERRORS = (InstagramFetchError, ThreadsFetchError)


class UnsupportedLinkError(ValueError):
    pass


class LinkScraper(LoggerMixin):
    """Single entry point for scraping: one url (`scrap`) or a batch (`scrap_bulk`).

    With a `pg_manager`, every request's outcome is upserted into `scraper_statuses`.
    """

    def __init__(
        self,
        aiohttp_client: aiohttp.ClientSession,
        pg_manager: "PostgresManager | None" = None,
    ):
        self.aiohttp_client = aiohttp_client
        self.pg_manager = pg_manager

    @staticmethod
    def classify_platform(url: str) -> Platform:
        if instagram_settings.SHORTCODE_RE.search(url):
            return Platform.INSTAGRAM
        if threads_settings.SHORTCODE_RE.search(url) or threads_settings.SHARE_RE.search(url):
            return Platform.THREADS
        raise UnsupportedLinkError(f"No scraper supports {url!r}")

    async def scrap(self, url: str) -> ScrapedPost:
        """Dispatch `url` to the matching platform scraper, record the outcome, normalize."""
        platform = self.classify_platform(url)
        try:
            match platform:
                case Platform.INSTAGRAM:
                    data = await self.scrap_instagram_reel(url)
                case Platform.THREADS:
                    data = await self.scrap_threads_post(url)
        except ScraperStatusError:
            await self._record_status(platform, ProcessingStatus.FAILED)
            raise
        except _POST_LEVEL_ERRORS:
            await self._record_status(platform, ProcessingStatus.SUCCESS)
            raise
        await self._record_status(platform, ProcessingStatus.SUCCESS)
        return ScrapedPost.from_scraper(data)

    async def scrap_bulk(self, urls: list[str]) -> list[ScrapedPost | Exception]:
        """Scrape `urls`; results (or exceptions) come back in input order.

        Platforms run in parallel, each one sequentially (its limiters serialize requests
        anyway). After a `ScraperStatusError` the rest of that platform's urls are not requested
        and get an "aborted" `ScraperStatusError` instead; other platforms continue.
        """
        results: list[ScrapedPost | Exception | None] = [None] * len(urls)
        by_platform: dict[Platform, list[tuple[int, str]]] = defaultdict(list)
        for index, url in enumerate(urls):
            try:
                by_platform[self.classify_platform(url)].append((index, url))
            except UnsupportedLinkError as e:
                results[index] = e

        await asyncio.gather(
            *[
                self._scrap_platform_batch(
                    platform,
                    batch,
                    results,
                )
                for platform, batch in by_platform.items()
            ]
        )
        return results

    async def _scrap_platform_batch(
        self,
        platform: Platform,
        batch: list[tuple[int, str]],
        results: list,
    ) -> None:
        for position, (index, url) in enumerate(batch):
            try:
                results[index] = await self.scrap(url)
            except ScraperStatusError as e:
                results[index] = e
                remaining = batch[position + 1 :]
                for skipped_index, _ in remaining:
                    results[skipped_index] = ScraperStatusError(platform, f"aborted: {e.message}")
                self.log_warning(
                    "Platform aborted",
                    platform=platform,
                    aborted=len(remaining),
                    reason=e.message,
                )
                return
            except Exception as e:
                results[index] = e

    async def _record_status(self, platform: Platform, status: ProcessingStatus) -> None:
        """Upsert `scraper_statuses`; a DB failure is logged and never masks the scrape result."""
        if self.pg_manager is None:
            return
        try:
            await self.pg_manager.upsert_scraper_status(platform, status)
        except Exception as e:
            self.log_error(
                "Could not record scraper status",
                error=e,
                platform=platform,
                status=status,
            )

    async def scrap_instagram_reel(self, url: str) -> ReelData:
        try:
            reel = await instagram_graphql.fetch_reel(url, session=self.aiohttp_client)
        except (InstagramFetchError, ScraperStatusError) as e:
            self.log_error(
                "Instagram scrape failed",
                error=e,
                url=url,
            )
            raise
        self.log_info(
            "Scraped Instagram reel",
            shortcode=reel.shortcode,
            url=url,
        )
        return reel

    async def scrap_threads_post(self, url: str) -> ThreadsPost:
        try:
            post = await threads.fetch_post(url, session=self.aiohttp_client)
        except (ThreadsFetchError, ScraperStatusError) as e:
            self.log_error(
                "Threads scrape failed",
                error=e,
                url=url,
            )
            raise
        self.log_info(
            "Scraped Threads post",
            shortcode=post.shortcode,
            media=len(post.media),
            url=url,
        )
        return post
