from enum import Enum

from pydantic import BaseModel, ConfigDict
from qdrant_client import models

from src.embedders.models import EmbeddersEnum


class RegisteredCollection(str, Enum):
    COSMOS_ZERO_VIDEO = "cosmos_zero"


class QdrantCollection(BaseModel):
    model_config = ConfigDict(frozen=True)

    collection_name: RegisteredCollection
    vectors_config: models.VectorParams
    embedder: EmbeddersEnum


QDRANT_COLLECTIONS: tuple[QdrantCollection] = tuple(
        QdrantCollection(
                collection_name=RegisteredCollection.COSMOS_ZERO_VIDEO,
                embedder=EmbeddersEnum.COSMOS_EMBED1_448P,
                vectors_config=models.VectorParams(
                        size=EmbeddersEnum.COSMOS_EMBED1_448P.get_dim(),
                        distance=models.Distance.COSINE
                ),
        )
)
