"""MLX backends (Apple Silicon, `uv sync --group mlx`). mlx packages are imported inside
methods so the rest of the package imports on machines without them."""

from pathlib import Path

import numpy as np
from PIL import Image

from src.recipe_parser.backends.base import (
    FrameReader,
    TextGenerator,
    Transcriber,
    restrict_language,
)
from src.recipe_parser.models import ParserModelsEnum
from src.recipe_parser.prompts import ASR_LANGUAGES, OCR_PROMPT, PADDLE_OCR_PROMPT, Message

OCR_MAX_NEW_TOKENS = 256


def _clear_mlx_cache() -> None:
    import mlx.core as mx

    mx.clear_cache()


class MlxWhisperTranscriber(Transcriber):
    def __init__(self, model: ParserModelsEnum):
        super().__init__(model)
        self.path: Path | None = None

    def _load(self) -> None:
        import mlx.core as mx
        from mlx_whisper.transcribe import ModelHolder

        self.path = self.download()
        ModelHolder.get_model(str(self.path), mx.float16)

    def _unload(self) -> None:
        from mlx_whisper.transcribe import ModelHolder

        ModelHolder.model = None
        ModelHolder.model_path = None

    def _free_device_memory(self) -> None:
        _clear_mlx_cache()

    def _detect_language(self, audio: np.ndarray) -> str:
        import mlx.core as mx
        from mlx_whisper.audio import N_FRAMES, N_SAMPLES, log_mel_spectrogram, pad_or_trim
        from mlx_whisper.transcribe import ModelHolder

        model = ModelHolder.get_model(str(self.path), mx.float16)
        mel = log_mel_spectrogram(
            audio,
            n_mels=model.dims.n_mels,
            padding=N_SAMPLES,
        )
        segment = pad_or_trim(
            mel,
            N_FRAMES,
            axis=-2,
        ).astype(mx.float16)
        _, probs = model.detect_language(segment)
        scores = {lang: probs.get(lang, 0.0) for lang in ASR_LANGUAGES}
        return restrict_language(max(scores, key=scores.get))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        import mlx_whisper

        self.load()
        if audio.size == 0:
            return ""
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=str(self.path),
            language=self._detect_language(audio),
            task="transcribe",
            verbose=None,
        )
        return result["text"].strip()


class MlxTextGenerator(TextGenerator):
    """mlx-lm chat model for the recipe JSON stage."""

    def __init__(self, model: ParserModelsEnum):
        super().__init__(model)
        self.model = None
        self.tokenizer = None

    def _load(self) -> None:
        from mlx_lm import load

        self.model, self.tokenizer = load(str(self.download()))

    def _unload(self) -> None:
        self.model = None
        self.tokenizer = None

    def _free_device_memory(self) -> None:
        _clear_mlx_cache()

    def generate(self, messages: list[Message], max_new_tokens: int) -> str:
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        self.load()
        prompt = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=False,
            enable_thinking=False,
        )
        return generate(
            self.model,
            self.tokenizer,
            prompt,
            max_tokens=max_new_tokens,
            sampler=make_sampler(temp=0.0),
        ).strip()


class MlxFrameReader(FrameReader):
    """mlx-vlm vision model for OCR on keyframes."""

    def __init__(self, model: ParserModelsEnum):
        super().__init__(model)
        self.model = None
        self.processor = None

    @property
    def is_paddle(self) -> bool:
        return "PaddleOCR" in self.repo

    def _load(self) -> None:
        from mlx_vlm import load

        self.model, self.processor = load(str(self.download()))

    def _unload(self) -> None:
        self.model = None
        self.processor = None

    def _free_device_memory(self) -> None:
        _clear_mlx_cache()

    def read_frame(self, image: Image.Image) -> str:
        from mlx_vlm import apply_chat_template, generate

        self.load()
        text = PADDLE_OCR_PROMPT if self.is_paddle else OCR_PROMPT
        prompt = apply_chat_template(
            self.processor,
            self.model.config,
            text,
            num_images=1,
            enable_thinking=False,
        )
        result = generate(
            self.model,
            self.processor,
            prompt,
            image=[image],
            max_tokens=OCR_MAX_NEW_TOKENS,
            temperature=0.0,
            verbose=False,
        )
        return result.text.strip()
