from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

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
