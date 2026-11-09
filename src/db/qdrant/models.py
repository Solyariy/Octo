from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from qdrant_client import models

from src.embedders.models import EmbeddersEnum


class RegisteredCollection(StrEnum):
    # StrEnum, not (str, Enum): on Python 3.12+ the latter stringifies as
    # `RegisteredCollection.MEMBER`, which the client sends as the collection name.
    COSMOS_ZERO_VIDEO = "cosmos_zero"
    GEMMA2_OMNI = "gemma2_omni"


class QdrantCollection(BaseModel):
    model_config = ConfigDict(frozen=True)

    collection_name: RegisteredCollection
    vectors_config: models.VectorParams
    embedder: EmbeddersEnum


def _cosine_collection(name: RegisteredCollection, embedder: EmbeddersEnum) -> QdrantCollection:
    return QdrantCollection(
            collection_name=name,
            embedder=embedder,
            vectors_config=models.VectorParams(
                    size=embedder.get_dim(), distance=models.Distance.COSINE
            ),
    )


QDRANT_COLLECTIONS: tuple[QdrantCollection, ...] = (
        _cosine_collection(
                RegisteredCollection.COSMOS_ZERO_VIDEO, EmbeddersEnum.COSMOS_EMBED1_448P
        ),
        _cosine_collection(RegisteredCollection.GEMMA2_OMNI, EmbeddersEnum.GEMMA2_OMNI),
)

_COLLECTIONS_BY_EMBEDDER = {c.embedder: c for c in QDRANT_COLLECTIONS}

# Indexed payload fields every collection carries (see QdrantPayload); ensured on every startup.
PAYLOAD_INDEXES: dict[str, models.PayloadSchemaType] = {
        "user_id": models.PayloadSchemaType.KEYWORD,
        "post_id": models.PayloadSchemaType.KEYWORD,
        "platform": models.PayloadSchemaType.KEYWORD,
        "modality": models.PayloadSchemaType.KEYWORD,
        "media_index": models.PayloadSchemaType.INTEGER,
        "created_at": models.PayloadSchemaType.DATETIME,
}


def get_collection(embedder: EmbeddersEnum) -> QdrantCollection:
    try:
        return _COLLECTIONS_BY_EMBEDDER[embedder]
    except KeyError:
        raise ValueError(f"No Qdrant collection registered for {embedder.value}") from None
