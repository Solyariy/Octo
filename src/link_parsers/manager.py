import aiohttp

from src.utils.logs import LoggerMixin


class LinkDownloader(LoggerMixin):
    def __init__(self, aiohttp_client: aiohttp.ClientSession):
        self.aiohttp_client = aiohttp_client

    def load_ig_reels(self, urls: list[str]):
        pass

