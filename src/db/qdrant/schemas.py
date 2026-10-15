import numpy as np
from pydantic import BaseModel, field_validator

from src.utils.annotations import StrUUID


class QdrantVector(BaseModel):
    id: StrUUID
    vector: list[float]

    @field_validator("vector", mode="before")
    @classmethod
    def _ndarray_to_list(cls, v):
        return v.tolist() if isinstance(v, np.ndarray) else v