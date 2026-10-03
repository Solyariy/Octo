from pydantic import BaseModel, ConfigDict
from qdrant_client import models

from src.embedders.models import EmbeddersEnum


class QdrantCollection(BaseModel):
    model_config = ConfigDict(frozen=True)

    collection_name: str
    vectors_config: models.VectorParams


QDRANT_COLLECTIONS: dict[EmbeddersEnum, QdrantCollection] = {
        EmbeddersEnum.COSMOS_EMBED1_448P:
        QdrantCollection(
                collection_name="cosmos_zero",
                vectors_config=models.VectorParams(
                        size=EmbeddersEnum.COSMOS_EMBED1_448P.get_dim(),
                        distance=models.Distance.EUCLID
                ),
        )
}
