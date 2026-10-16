from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from src.db.postgres.schemas import Post
from src.enums import Modality, Platform
from src.link_scrapers.schemas import ScrapedPost
from src.utils.annotations import StrUUID


class PipelineStage(StrEnum):
    SCRAPE = "scrape"
    DOWNLOAD = "download"
    EMBED = "embed"
    STORE = "store"
    FINALIZE = "finalize"


class EmbeddingItem(BaseModel):
    """One thing to embed: the post caption (text) or a downloaded image/video (local path)."""

    post_id: UUID
    platform: Platform
    modality: Modality
    media_index: int
    content: str


class PostJob(BaseModel):
    """Per-post pipeline state; a job stops at its first failed stage."""

    post: Post
    scraped: ScrapedPost | None = None
    items: list[EmbeddingItem] = Field(default_factory=list)
    failed_stage: PipelineStage | None = None
    error: str | None = None
    stored: bool = False

    @property
    def is_active(self) -> bool:
        return self.failed_stage is None


class ProcessingAccepted(BaseModel):
    """`POST /process/all` response: grep the server log for `log_id` to trace the run."""

    log_id: StrUUID
    post_ids: list[StrUUID]
