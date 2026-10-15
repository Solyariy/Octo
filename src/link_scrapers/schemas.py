from pydantic import BaseModel, Field

from src.enums import Platform
from src.link_scrapers.scrapers.instagram_graphql import ReelData
from src.link_scrapers.scrapers.threads import ThreadsPost


class ScrapedPost(BaseModel):
    image_urls: list[str] = Field(default_factory=list)
    video_urls: list[str] = Field(default_factory=list)

    image_local_paths: list[str] = Field(default_factory=list)
    video_local_paths: list[str] = Field(default_factory=list)

    text: str | None = None
    platform: Platform

    @classmethod
    def from_scraper(cls, data: ReelData | ThreadsPost) -> "ScrapedPost":
        match data:
            case ReelData():
                return cls._from_instagram_reel(data)
            case ThreadsPost():
                return cls._from_threads_post(data)
            case _:
                raise TypeError(f"Unsupported scraper result {type(data).__name__}")

    @classmethod
    def _from_instagram_reel(cls, data: ReelData) -> "ScrapedPost":
        # A reel's thumbnail is only a preview; it counts as content for photo posts alone.
        video_urls = [data.video_url] if data.video_url else []
        image_urls = [data.thumbnail_url] if not video_urls and data.thumbnail_url else []
        return cls(
            image_urls=image_urls,
            video_urls=video_urls,
            text=data.caption,
            platform=Platform.INSTAGRAM,
        )

    @classmethod
    def _from_threads_post(cls, data: ThreadsPost) -> "ScrapedPost":
        return cls(
            image_urls=[m.url for m in data.media if m.kind == "image"],
            video_urls=[m.url for m in data.media if m.kind == "video"],
            text=data.text or None,
            platform=Platform.THREADS,
        )
