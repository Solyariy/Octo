from collections.abc import Sequence
from pathlib import Path

import numpy as np
import torch
import transformers
from transformers import AutoModel, AutoProcessor

from src.embedders.base import BaseEmbeddingManager
from src.embedders.models import EmbeddersEnum
from src.settings import main_settings
from src.utils.models import pick_device
from src.utils.video import sample_frames


Clip = Path | str | np.ndarray


def require_supported_transformers() -> None:
    """Cosmos-Embed1's remote code does not load under transformers 5.

    It imports `transformers.pytorch_utils.find_pruneable_heads_and_indices`
    (removed in 5) and relies on a load_state_dict pre-hook to interpolate
    `visual_encoder.pos_embed`, which the transformers 5 loader skips before
    aborting on the resulting size mismatch. `pyproject.toml` pins 4.x.
    """
    major = int(transformers.__version__.split(".")[0])
    if major >= 5:
        raise RuntimeError(
            f"Cosmos-Embed1 requires transformers 4.x, found {transformers.__version__}. "
            "Run `uv sync` to install the pinned version."
        )


class CosmosEmbeddingManager(BaseEmbeddingManager):
    """`trust_remote_code` backend for nvidia/Cosmos-Embed1-*.

    Text and video land in one shared space, so `encode_text` and
    `encode_video` outputs are directly comparable. Both are L2-normalised by
    the model. Weights use the HuggingFace cache layout under `MODELS_PATH`
    rather than the `MODELS_PATH/<model-id>` layout of the sentence-transformers
    backend, because `save_pretrained` does not round-trip a remote-code model
    together with its processor.
    """

    def __init__(self, model_registry: EmbeddersEnum):
        super().__init__(model_registry)
        self.processor = None
        self.device, self.dtype = pick_device()

    @property
    def num_frames(self) -> int:
        """Frames per clip the video tower expects."""
        self.load_model()
        return self.model.config.num_video_frames

    def load_model(self) -> None:
        if self.model is not None:
            return

        require_supported_transformers()
        self.log_info(
            "Loading model",
            model=self.model_registry.value,
            device=str(self.device),
            dtype=str(self.dtype),
        )
        kwargs = dict(
            trust_remote_code=True,
            cache_dir=main_settings.MODELS_PATH,
            token=main_settings.HF_AUTH_TOKEN,
            **self.model_registry.get_config(),
        )
        self.model = AutoModel.from_pretrained(self.model_registry.value, **kwargs).to(
            self.device, dtype=self.dtype
        )
        self.processor = AutoProcessor.from_pretrained(self.model_registry.value, **kwargs)

    def encode_text(self, texts: list[str], **kwargs) -> np.ndarray:
        self.load_model()
        inputs = self.processor(text=list(texts)).to(self.device, dtype=self.dtype)
        with torch.inference_mode():
            output = self.model.get_text_embeddings(**inputs)
        return output.text_proj.float().cpu().numpy()

    def encode_video(self, videos: Sequence[Clip], **kwargs) -> np.ndarray:
        """Embed clips given as file paths or as THWC uint8 frame arrays."""
        self.load_model()
        clips = np.stack([self._as_frames(video) for video in videos])
        batch = np.transpose(clips, (0, 1, 4, 2, 3))  # BTHWC -> BTCHW

        inputs = self.processor(videos=batch).to(self.device, dtype=self.dtype)
        with torch.inference_mode():
            output = self.model.get_video_embeddings(**inputs)
        return output.visual_proj.float().cpu().numpy()

    def _as_frames(self, video: Clip) -> np.ndarray:
        if isinstance(video, (str, Path)):
            return sample_frames(video, self.num_frames)
        if isinstance(video, np.ndarray) and video.ndim == 4:
            return video
        raise TypeError("Expected a video path or a THWC frame array, got " f"{type(video).__name__}")

    def unload(self) -> None:
        super().unload()
        self.processor = None
