import numpy as np
from qdrant_client import models

from src.db.qdrant.init_db import async_qdrant_client
from src.db.qdrant.models import QDRANT_COLLECTIONS
from src.embedders.models import EmbeddersEnum
from src.utils.logs import LoggerMixin
from src.utils.order import get_uuid_str


class QdrantManager(LoggerMixin):
    @property
    def client(self):
        return async_qdrant_client

    async def upsert_vectors(self, embedder_info: EmbeddersEnum, vectors: np.ndarray):
        result = await self.client.upsert(
            collection_name=QDRANT_COLLECTIONS[embedder_info].collection_name,
            points=[
                models.PointStruct(
                    id=get_uuid_str(),
                    vector=vector.tolist(),
                ) for vector in vectors
            ]
        )
        self.log_info("Upsert result", result=result.model_dump(mode="json"))
        return result
