import numpy as np
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.db.postgres.schemas import UserInfo
from src.db.qdrant.models import QdrantCollection
from src.db.qdrant.schemas import QdrantVector
from src.utils.logs import LoggerMixin


class QdrantManager(LoggerMixin):

    def __init__(self, qdrant_client: AsyncQdrantClient):
        self.client = qdrant_client

    async def upsert_vectors(
            self, collection: QdrantCollection,
            vectors: list[QdrantVector],
            user_info: UserInfo,
    ):
        result = await self.client.upsert(
            collection_name=collection.collection_name,
            points=[
                models.PointStruct(
                    id=vector.point_id,
                    vector=vector.vector,
                    payload=vector.payload(user_id=str(user_info.id)),
                ) for vector in vectors
            ]
        )
        self.log_info(
            "Vectors upserted",
            collection=collection.collection_name.value,
            user_id=str(user_info.id),
            points=len(vectors),
            post_ids=sorted(
                {str(v.post_id)
                 for v in vectors}
                ),
            result=result.model_dump(mode="json"),
        )
        return result

    async def find_similar(
            self, collection: QdrantCollection, query_vector: np.ndarray, user_info: UserInfo,
    ):
        results = await self.client.query_points(
            collection_name=collection.collection_name,
            query=query_vector,
            limit=15,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id", match=MatchValue(value=str(user_info.id))
                    )
                ]
            )
        )
        if results.points:
            best_score = max(p.score for p in results.points)
            worst_score = min(p.score for p in results.points)
            self.log_info(
                "Similarity search results",
                count=len(results.points),
                best_score=best_score,
                worst_score=worst_score
            )
        else:
            self.log_warning("Similarity search returned empty", count=len(results.points))
        return results
