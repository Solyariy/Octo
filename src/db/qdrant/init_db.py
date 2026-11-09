from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from grpc import RpcError
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from src.db.qdrant.models import PAYLOAD_INDEXES, QDRANT_COLLECTIONS, QdrantCollection
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
    for collection in QDRANT_COLLECTIONS:
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
            await _ensure_payload_indexes(client, collection)
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
    await _ensure_payload_indexes(client, collection)


async def _ensure_payload_indexes(client: AsyncQdrantClient, collection: QdrantCollection) -> None:
    """Create every `PAYLOAD_INDEXES` entry the collection lacks; additive, never drops one.

    Runs for existing collections too, so a field added to the registry gets indexed on the
    next startup. An index already present under a different type is logged, not replaced.
    """
    info = await client.get_collection(collection.collection_name)
    existing = info.payload_schema or {}
    for field_name, field_schema in PAYLOAD_INDEXES.items():
        current = existing.get(field_name)
        if current is None:
            await client.create_payload_index(
                    collection_name=collection.collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
            )
            Logger.info(
                    "Created Qdrant payload index",
                    collection=collection.collection_name,
                    field=field_name,
                    schema=field_schema,
            )
        elif current.data_type != field_schema:
            Logger.warning(
                    "Qdrant payload index type differs from the registry; leaving it as is",
                    collection=collection.collection_name,
                    field=field_name,
                    expected=field_schema,
                    actual=current.data_type,
            )


async def _assert_collection_matches(
        client: AsyncQdrantClient,
        collection: QdrantCollection,
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
