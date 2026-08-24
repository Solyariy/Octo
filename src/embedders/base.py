from abc import ABC, abstractmethod
from typing import Any, Self

from src.embedders.models import EmbeddersEnum
from src.utils.logs import LoggerMixin


class BaseEmbeddingManager(LoggerMixin, ABC):
    """Shared lifecycle for every embedding backend.

    Subclasses own loading and encoding; everything here is backend-agnostic.
    Use as a context manager so `unload()` always runs.
    """

    def __init__(self, model_registry: EmbeddersEnum):
        self.model_registry = model_registry
        self.model: Any | None = None

    @property
    def output_dim(self) -> int:
        return self.model_registry.get_dim()

    @abstractmethod
    def load_model(self) -> None:
        """Idempotent: a second call on a loaded manager must be a no-op."""

    @abstractmethod
    def encode_text(self, texts: list[str], **kwargs):
        """Return one `output_dim` vector per text."""

    def encode_video(self, videos, **kwargs):
        """Return one `output_dim` vector per clip, for backends that have a video tower."""
        raise NotImplementedError(f"{type(self).__name__} does not support video embeddings")

    def unload(self) -> None:
        self.model = None

    def __enter__(self) -> Self:
        self.load_model()
        return self

    def __exit__(self, *exc) -> None:
        self.unload()
