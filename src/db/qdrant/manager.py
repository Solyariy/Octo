import numpy as np
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import FieldCondition, MatchValue

from src.db.postgres.schemas import UserInfo
from src.db.qdrant.filters import QdrantFilter
from src.db.qdrant.models import QdrantCollection
from src.db.qdrant.schemas import QdrantVector, ScoredPostHit
from src.utils.logs import LoggerMixin


class QdrantManager(LoggerMixin):
    def __init__(self, qdrant_client: AsyncQdrantClient):
        self.client = qdrant_client

    async def upsert_vectors(
        self,
        collection: QdrantCollection,
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
                )
                for vector in vectors
            ],
        )
        self.log_info(
            "Vectors upserted",
            collection=collection.collection_name.value,
            user_id=str(user_info.id),
            points=len(vectors),
            post_ids=sorted({str(v.post_id) for v in vectors}),
            result=result.model_dump(mode="json"),
        )
        return result

    async def search_posts(
        self,
        collection: QdrantCollection,
        query_vector: np.ndarray,
        user_info: UserInfo,
        point_filter: QdrantFilter,
        limit: int,
        offset: int,
    ) -> list[ScoredPostHit]:
        """Rank the user's posts by their best-matching point, payload filter applied in Qdrant.

        Grouped by `post_id` so a post with a caption and several media fills one slot.
        `query_points_groups` has no offset, so the first `offset + limit` groups are fetched
        and sliced; callers cap `limit` and the page depth through their pagination params.
        """
        user_scope = FieldCondition(key="user_id", match=MatchValue(value=str(user_info.id)))
        result = await self.client.query_points_groups(
            collection_name=collection.collection_name,
            group_by="post_id",
            query=query_vector,
            query_filter=point_filter.filter_qdrant(must=[user_scope]),
            limit=offset + limit,
            group_size=1,
            with_payload=["modality", "media_index"],
        )
        hits = [
            ScoredPostHit(
                post_id=str(group.id),
                score=group.hits[0].score,
                modality=group.hits[0].payload["modality"],
                media_index=group.hits[0].payload["media_index"],
            )
            for group in result.groups[offset:]
            if group.hits
        ]
        if hits:
            self.log_info(
                "Similarity search results",
                collection=collection.collection_name.value,
                count=len(hits),
                best_score=hits[0].score,
                worst_score=hits[-1].score,
            )
        else:
            self.log_info(
                "Similarity search returned empty",
                collection=collection.collection_name.value,
                offset=offset,
            )
        return hits
