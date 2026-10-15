
import numpy as np
from qdrant_client import AsyncQdrantClient, models

from src.db.qdrant.models import QdrantCollection
from src.db.qdrant.schemas import QdrantVector
from src.utils.logs import LoggerMixin


class QdrantManager(LoggerMixin):
    def __init__(self, qdrant_client: AsyncQdrantClient):
        self.client = qdrant_client

    async def upsert_vectors(self, collection: QdrantCollection, vectors: list[QdrantVector]):
        result = await self.client.upsert(
                collection_name=collection.collection_name,
                points=[
                        models.PointStruct(
                                id=vector.id,
                                vector=vector.vector,
                        ) for vector in vectors
                ]
        )
        self.log_info("Upsert result", result=result.model_dump(mode="json"))
        return result

    async def find_similar(self, collection: QdrantCollection, query_vector: np.ndarray):
        results = await self.client.query_points(
            collection_name=collection.collection_name,
            query=query_vector,
            limit=15
        )
        if results.points:
            best_score = max(p.score for p in results.points)
            worst_score = min(p.score for p in results.points)
            self.log_info("Similarity search results", count=len(results.points), best_score=best_score, worst_score=worst_score)
        else:
            self.log_warning("Similarity search returned empty", count=len(results.points))
        return results
