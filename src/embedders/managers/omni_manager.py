import math
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image

from src.embedders.managers.hf_manager import GeneralEmbeddingManager
from src.enums import Modality
from src.utils.video import sample_frames, video_duration

OmniInput = tuple[Modality, str | Path]


class OmniEmbeddingManager(GeneralEmbeddingManager):
    """sentence-transformers backend for multimodal models (EmbeddingGemma 2).

    Text, images and video land in one L2-normalised space, so any two vectors are
    comparable by dot product. Videos are decoded here with PyAV and handed over as PIL
    frames: the library's own path/URL video decoding needs torchcodec, which must stay
    uninstalled.
    """

    # Model defaults: 1 frame per second, at most 32 frames per clip.
    VIDEO_MAX_FRAMES = 32
    # Clips are decoded and encoded this many at a time to bound frame memory.
    VIDEO_CHUNK_SIZE = 4
    DOCUMENT_PROMPT = "Document"

    def encode_inputs(self, inputs: Sequence[OmniInput], **kwargs) -> np.ndarray:
        """Embed a mixed batch; row `i` of the result belongs to `inputs[i]`.

        Inputs are grouped by modality because the text prompt applies to text only.
        """
        self.load_model()
        result = np.zeros((len(inputs), self.output_dim), dtype=np.float32)
        groups: dict[Modality, list[int]] = {}
        for index, (modality, _) in enumerate(inputs):
            groups.setdefault(Modality(modality), []).append(index)

        for modality, indices in groups.items():
            values = [inputs[i][1] for i in indices]
            started = time.perf_counter()
            match modality:
                case Modality.TEXT:
                    vectors = self.encode_text(values, **kwargs)
                case Modality.IMAGE:
                    vectors = self.encode_image(values, **kwargs)
                case Modality.VIDEO:
                    vectors = self.encode_video(values, **kwargs)
            result[indices] = vectors
            self.log_info(
                    "Encoded modality group",
                    modality=modality,
                    count=len(indices),
                    duration_ms=round((time.perf_counter() - started) * 1000),
            )
        return result

    def encode_text(self, texts: list[str], **kwargs) -> np.ndarray:
        kwargs.setdefault("prompt_name", self.DOCUMENT_PROMPT)
        return super().encode_text(list(texts), **kwargs)

    def encode_image(self, images: Sequence[str | Path], **kwargs) -> np.ndarray:
        self.load_model()
        pil_images = []
        for path in images:
            with Image.open(path) as image:
                pil_images.append(image.convert("RGB"))
        return self._encode([{"image": image} for image in pil_images], **kwargs)

    def encode_video(self, videos: Sequence[str | Path], **kwargs) -> np.ndarray:
        self.load_model()
        chunks = []
        for start in range(0, len(videos), self.VIDEO_CHUNK_SIZE):
            batch = [self._as_video_input(v) for v in videos[start:start + self.VIDEO_CHUNK_SIZE]]
            chunks.append(self._encode(batch, **kwargs))
        return np.concatenate(chunks) if chunks else np.zeros((0, self.output_dim), np.float32)

    def _encode(self, inputs: list[dict], **kwargs) -> np.ndarray:
        return self.model.encode(inputs, **kwargs, truncate_dim=self.output_dim)

    def _as_video_input(self, path: str | Path) -> dict:
        duration = max(video_duration(path), 1e-3)
        num_frames = min(self.VIDEO_MAX_FRAMES, max(1, math.ceil(duration)))
        frames = [Image.fromarray(frame) for frame in sample_frames(path, num_frames)]
        metadata = {
                "fps": num_frames / duration,
                "total_num_frames": num_frames,
                "duration": duration
        }
        return {"video": {"array": frames, "video_metadata": metadata}}
