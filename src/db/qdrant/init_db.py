from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from grpc import RpcError
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from src.db.qdrant.models import QDRANT_COLLECTIONS, QdrantCollection
from src.settings import db_settings
from src.utils.logs import Logger


class QdrantCollectionMismatchError(RuntimeError):
    """An existing Qdrant collection does not match its configured spec."""


def build_qdrant_client() -> AsyncQdrantClient:
    api_key = db_settings.QDRANT_API_KEY
    return AsyncQdrantClient(
            url=db_settings.QDRANT_URL,
            prefer_grpc=db_settings.QDRANT_PREFER_GRPC,
            api_key=api_key.get_secret_value() if api_key is not None else None,
            timeout=db_settings.QDRANT_TIMEOUT,
            pool_size=db_settings.QDRANT_POOL_SIZE,
            check_compatibility=db_settings.QDRANT_CHECK_COMPATIBILITY,
    )


@asynccontextmanager
async def qdrant_client_lifespan() -> AsyncIterator[AsyncQdrantClient]:
    """App-scoped client: enter once in the app lifespan, never inside a request.

    `AsyncQdrantClient` is not itself an async context manager, so the close has
    to be wrapped by hand.
    """
    client = build_qdrant_client()
    try:
        yield client
    finally:
        await client.close()


async def init_qdrant_collections(client: AsyncQdrantClient) -> None:
    """Create missing collections and validate the ones that already exist.

    Sequential on purpose: a failure names the offending collection instead of
    leaving siblings mid-flight the way `asyncio.gather` would.
    """
    for collection in QDRANT_COLLECTIONS.values():
        await _ensure_collection(client, collection)


async def _ensure_collection(client: AsyncQdrantClient, collection: QdrantCollection) -> None:
    if not await client.collection_exists(collection.collection_name):
        try:
            # Pass vectors_config as the model, never **collection.model_dump():
            # a flattened VectorParams reaches the gRPC path as a named-vectors
            # mapping and blows up in RestToGrpc.convert_vectors_config.
            await client.create_collection(
                    collection_name=collection.collection_name,
                    vectors_config=collection.vectors_config,
            )
            Logger.info("Created Qdrant collection", collection=collection.collection_name)
            return
        except (UnexpectedResponse, RpcError):
            # Re-probe rather than matching a status code: this tells "another
            # worker won the create race" apart from "the server rejected the
            # spec" under both REST and gRPC.
            if not await client.collection_exists(collection.collection_name):
                raise
            Logger.warning(
                    "Collection creation raced with another worker; validating instead",
                    collection=collection.collection_name,
            )

    await _assert_collection_matches(client, collection)


async def _assert_collection_matches(
        client: AsyncQdrantClient, collection: QdrantCollection
) -> None:
    info = await client.get_collection(collection.collection_name)
    actual = info.config.params.vectors
    expected = collection.vectors_config

    # `vectors` is VectorParams | dict[str, VectorParams] | None; a named-vectors
    # collection would silently break QdrantManager's unnamed PointStruct upserts.
    if (not isinstance(actual, models.VectorParams) or actual.size != expected.size
                or actual.distance != expected.distance):
        raise QdrantCollectionMismatchError(
                f"Collection {collection.collection_name!r} exists with vectors={actual!r}, "
                f"but the registry expects size={expected.size} distance={expected.distance}. "
                "Refusing to modify it - migrate or drop it manually."
        )
