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

# Keyword-indexed payload fields every collection carries (see QdrantManager.upsert_vectors).
PAYLOAD_INDEX_FIELDS: tuple[str, ...] = ("user_id", "post_id", "platform", "modality")


def get_collection(embedder: EmbeddersEnum) -> QdrantCollection:
    try:
        return _COLLECTIONS_BY_EMBEDDER[embedder]
    except KeyError:
        raise ValueError(f"No Qdrant collection registered for {embedder.value}") from None
