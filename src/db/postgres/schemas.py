from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field

from src.enums import Platform, ProcessingStatus


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    email: str


class PostIdUrl(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str


class Post(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    url: str
    platform: Platform
    status: ProcessingStatus
    created_at: datetime


class Task(BaseModel):
    """A processing batch; `status` is derived from the counts, never stored."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: str
    user_id: UUID
    created_at: datetime
    total_count: int
    success_count: int
    failed_count: int

    @computed_field
    @property
    def status(self) -> ProcessingStatus:
        if self.success_count + self.failed_count < self.total_count:
            return ProcessingStatus.IN_PROCESS
        if self.failed_count:
            return ProcessingStatus.FAILED
        return ProcessingStatus.SUCCESS


class TaskPost(BaseModel):
    """A post plus its outcome in one task (`stage`/`error` set only when it failed there)."""

    post: Post
    status: ProcessingStatus
    stage: str | None
    error: str | None


class TaskDetail(Task):
    posts: list[TaskPost]


class ScraperStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: Platform
    last_request_status: ProcessingStatus
    updated_at: datetime
