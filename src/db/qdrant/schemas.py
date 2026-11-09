import uuid
from datetime import datetime

import numpy as np
from pydantic import BaseModel, computed_field, field_validator

from src.enums import Modality, Platform
from src.utils.annotations import StrUUID


class QdrantPayload(BaseModel):
    """The payload every point carries; filterable through `src.db.qdrant.filters`."""

    user_id: StrUUID
    post_id: StrUUID
    platform: Platform
    modality: Modality
    media_index: int
    created_at: datetime


class QdrantVector(BaseModel):
    post_id: StrUUID
    platform: Platform
    modality: Modality
    media_index: int
    created_at: datetime
    vector: list[float]

    @computed_field
    @property
    def point_id(self) -> StrUUID:
        """Deterministic, so re-processing a post overwrites its points instead of duplicating."""
        return str(
                uuid.uuid5(
                        uuid.NAMESPACE_URL, f"{self.post_id}:{self.modality}:{self.media_index}"
                )
        )

    def payload(self, user_id: StrUUID) -> dict:
        # mode="json": enums as values, created_at as an RFC 3339 string for the DATETIME index.
        return QdrantPayload(
                user_id=str(user_id),
                post_id=str(self.post_id),
                platform=self.platform,
                modality=self.modality,
                media_index=self.media_index,
                created_at=self.created_at,
        ).model_dump(mode="json")

    @field_validator("vector", mode="before")
    @classmethod
    def _ndarray_to_list(cls, v):
        return v.tolist() if isinstance(v, np.ndarray) else v


class ScoredPostHit(BaseModel):
    """Best-matching point of one post in a similarity search."""

    post_id: StrUUID
    score: float
    modality: Modality
    media_index: int
