import os
import shutil

from pathlib import Path

from sentence_transformers import SentenceTransformer

from src.embedders.managers.base import BaseEmbeddingManager
from src.embedders.models import EmbeddersEnum
from src.settings import main_settings
from src.utils.order import get_model_path


class GeneralEmbeddingManager(BaseEmbeddingManager):
    """sentence-transformers backend: text only, cached at `MODELS_PATH/<model-id>`."""

    def __init__(self, embedder_info: EmbeddersEnum):
        super().__init__(embedder_info)
        self.model: SentenceTransformer | None = None

    def load_model(self) -> None:
        if self.model is not None:
            return

        path = get_model_path(self.embedder_info.value)
        if os.path.isdir(path):
            self.log_info("Loading model from disk", path=str(path))
            self.model = SentenceTransformer(str(path), **self.embedder_info.get_config())
        else:
            self.log_info("Downloading model from hub", model=self.embedder_info.value)
            self.model = self._download_and_save(path)

    def _download_and_save(self, dest: Path) -> SentenceTransformer:
        model = SentenceTransformer(self.embedder_info.value, **self.embedder_info.get_config(), use_auth_token=main_settings.HF_AUTH_TOKEN)

        # Save atomically: write to a sibling .part dir, then move into place.
        # Prevents a partially-written dir from being mistaken for a valid model.
        tmp = dest.with_name(dest.name + ".part")
        try:
            model.save_pretrained(str(tmp))
            shutil.move(str(tmp), str(dest))
            self.log_info("Model saved", path=str(dest))
        except Exception as e:
            self.log_error(
                "Failed to persist downloaded model",
                error=e,
                model=self.embedder_info.value,
            )
            # Still keep the in-memory model usable so this run isn't wasted;
            # it will simply re-download on the next start.
            self.log_warning(
                "Keeping model in memory only; will re-download next run",
                model=self.embedder_info.value,
            )
            # Clean up any leftover partial directory.
            if os.path.exists(tmp):
                shutil.rmtree(tmp, ignore_errors=True)

        return model

    def encode_text(self, texts: list[str], **kwargs):
        self.load_model()
        return self.model.encode(texts, **kwargs, truncate_dim=self.output_dim)
