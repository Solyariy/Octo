from pydantic import BaseModel, computed_field, field_validator

from src.enums import Platform
from src.link_scrapers.manager import LinkScraper


class InputPost(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def _supported_platform(cls, url: str) -> str:
        # UnsupportedLinkError is a ValueError, so FastAPI answers 422 naming the url.
        url = url.strip()
        LinkScraper.classify_platform(url)
        return url

    @computed_field
    @property
    def platform(self) -> Platform:
        return LinkScraper.classify_platform(self.url)
