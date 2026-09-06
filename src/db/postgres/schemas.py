from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str


class MediaFile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    created_at: datetime
