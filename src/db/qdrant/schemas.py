import uuid

import numpy as np
from pydantic import BaseModel, computed_field, field_validator

from src.enums import Modality, Platform
from src.utils.annotations import StrUUID


class QdrantVector(BaseModel):
    post_id: StrUUID
    platform: Platform
    modality: Modality
    media_index: int
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
        return {
            "user_id": str(user_id),
            "platform": self.platform.value,
            "post_id": str(self.post_id),
            "modality": self.modality.value,
            "media_index": self.media_index,
        }

    @field_validator("vector", mode="before")
    @classmethod
    def _ndarray_to_list(cls, v):
        return v.tolist() if isinstance(v, np.ndarray) else v
