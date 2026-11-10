from src.enums import Platform


class ScraperStatusError(Exception):
    """The platform itself refused us (block, rate limit, bot check), not one post.

    Shared by every scraper. `LinkScraper.scrap_bulk` stops scraping `platform` for the rest of
    the batch when it sees one. Never retried: it is not an `aiohttp.ClientError`.
    """

    def __init__(self, platform: Platform, message: str):
        self.platform = platform
        self.message = message
        super().__init__(f"{platform} unavailable: {message}")
