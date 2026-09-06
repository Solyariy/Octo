import asyncio

import qdrant_client
from qdrant_client import AsyncQdrantClient
from contextlib import asynccontextmanager

from src.settings import db_settings

async_qdrant_client: AsyncQdrantClient = None


async def get_qdrant_client() -> AsyncQdrantClient:
    """Get or create the shared async Qdrant client."""
    global async_qdrant_client
    if async_qdrant_client is None:
        async_qdrant_client = AsyncQdrantClient(
            url=db_settings.QDRANT_URL,
            prefer_grpc=db_settings.QDRANT_PREFER_GRPC,
        )
    return async_qdrant_client


async def close_qdrant_client() -> None:
    """Close the shared async Qdrant client if it exists."""
    global async_qdrant_client
    if async_qdrant_client is not None:
        await async_qdrant_client.close()
        async_qdrant_client = None


@asynccontextmanager
async def get_qdrant_context_manager():
    client = await get_qdrant_client()
    yield client
    await close_qdrant_client()


async def init_qdrant_collections(client: AsyncQdrantClient):
    from src.db.qdrant.models import QdrantCollection, QDRANT_COLLECTIONS

    async def _task(coll: QdrantCollection, l_client: AsyncQdrantClient):
        exists = await l_client.collection_exists(coll.collection_name)
        if not exists:
            try:
                await l_client.create_collection(**coll.model_dump())
            except qdrant_client.http.exceptions.UnexpectedResponse:
                await l_client.delete_collection(coll.collection_name)
                await l_client.create_collection(**coll.model_dump())

    tasks = [_task(coll, client) for coll in QDRANT_COLLECTIONS.values()]
    await asyncio.gather(*tasks)
