from src.embedders.base import BaseEmbeddingManager
from src.embedders.cosmos_manager import CosmosEmbeddingManager
from src.embedders.hf_manager import GeneralEmbeddingManager
from src.embedders.models import Backend, EmbeddersEnum


MANAGERS: dict[Backend, type[BaseEmbeddingManager]] = {
    "sentence_transformers": GeneralEmbeddingManager,
    "cosmos": CosmosEmbeddingManager,
}


def get_embedding_manager(model: EmbeddersEnum) -> BaseEmbeddingManager:
    """Build the manager registered for `model`'s backend."""
    backend = model.get_backend()
    manager_cls = MANAGERS.get(backend)
    if manager_cls is None:
        raise ValueError(f"No manager registered for backend {backend!r} ({model.value})")
    return manager_cls(model)
