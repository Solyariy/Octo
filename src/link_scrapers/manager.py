import aiohttp

from src.utils.logs import LoggerMixin


class LinkScraper(LoggerMixin):

    def __init__(self, aiohttp_client: aiohttp.ClientSession):
        self.aiohttp_client = aiohttp_client

    @staticmethod
    def classify_platform(url: str):
        pass
