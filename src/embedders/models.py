from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

Backend = Literal["sentence_transformers", "cosmos"]


@dataclass(frozen=True)
class EmbedderSpec:
    """Everything the managers need to know about a registered model.

    `dim` is the vector length the manager is expected to emit, which is what
    vector-store collections are sized against. `load_kwargs` is passed
    verbatim to the backend loader.
    """

    backend: Backend
    dim: int
    load_kwargs: dict = field(default_factory=dict)


class EmbeddersEnum(str, Enum):
    QWEN3_8B = "Qwen/Qwen3-Embedding-8B"
    QWEN3_4B = "Qwen/Qwen3-Embedding-4B"
    JINA5_OMNI = "jinaai/jina-embeddings-v5-omni-small"
    GEMMA_03B = "google/embeddinggemma-300m"
    COSMOS_EMBED1_448P = "nvidia/Cosmos-Embed1-448p"

    def get_spec(self) -> EmbedderSpec:
        return EMBEDDING_MODEL_CONFIG[self]

    def get_config(self) -> dict:
        return dict(self.get_spec().load_kwargs)

    def get_dim(self) -> int:
        return self.get_spec().dim

    def get_backend(self) -> Backend:
        return self.get_spec().backend


EMBEDDING_MODEL_CONFIG: dict[EmbeddersEnum, EmbedderSpec] = {
        # Qwen3 embeddings are matryoshka-trained, so 2048 is a real truncation.
        EmbeddersEnum.QWEN3_8B:
        EmbedderSpec(backend="sentence_transformers", dim=2048),
        EmbeddersEnum.QWEN3_4B:
        EmbedderSpec(backend="sentence_transformers", dim=2048),
        # Unproven: dim not measured yet, truncation is a no-op if the model is smaller.
        EmbeddersEnum.JINA5_OMNI:
        EmbedderSpec(backend="sentence_transformers", dim=2048),
        EmbeddersEnum.GEMMA_03B:
        EmbedderSpec(backend="sentence_transformers", dim=768),
        EmbeddersEnum.COSMOS_EMBED1_448P:
        EmbedderSpec(backend="cosmos", dim=768),
}

_unregistered = [member.name for member in EmbeddersEnum if member not in EMBEDDING_MODEL_CONFIG]
if _unregistered:
    raise RuntimeError(
            f"EmbeddersEnum members without an EMBEDDING_MODEL_CONFIG entry: {_unregistered}"
    )
