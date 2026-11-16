import gc
from abc import ABC, abstractmethod
from pathlib import Path
from time import perf_counter
from typing import Self

import numpy as np
from huggingface_hub import snapshot_download
from PIL import Image

from src.recipe_parser.models import ParserModelsEnum
from src.recipe_parser.prompts import ASR_LANGUAGES, Message
from src.settings import main_settings
from src.utils.logs import LoggerMixin

# Whisper may detect a neighbouring language; map it back onto the two we accept.
_CYRILLIC_LANGUAGES = {"ru", "be", "bg", "mk", "sr", "kk"}


def restrict_language(detected: str | None) -> str:
    """Speech is English or Ukrainian only: Cyrillic look-alikes become `uk`, the rest `en`."""
    if detected in ASR_LANGUAGES:
        return detected
    return "uk" if detected in _CYRILLIC_LANGUAGES else "en"


class BaseParserModel(LoggerMixin, ABC):
    """Load/unload lifecycle shared by every recipe-parser backend.

    Weights live in the HuggingFace cache layout under `MODELS_PATH`. Use as a context manager
    so `unload()` always runs: the benchmark keeps one model in memory at a time.
    """

    def __init__(self, model: ParserModelsEnum):
        self.info = model
        self.spec = model.get_spec()
        self.load_seconds = 0.0
        self._loaded = False

    @property
    def repo(self) -> str:
        return self.spec.repo

    def download(self) -> Path:
        """Fetch (or reuse) the weights and return the local snapshot path."""
        return Path(
            snapshot_download(
                self.repo,
                cache_dir=main_settings.MODELS_PATH,
                token=main_settings.HF_AUTH_TOKEN.get_secret_value(),
            )
        )

    def load(self) -> None:
        if self._loaded:
            return
        self.log_info(
            "Loading model",
            model=self.info.value,
            repo=self.repo,
        )
        started = perf_counter()
        self._load()
        self.load_seconds = perf_counter() - started
        self._loaded = True
        self.log_info(
            "Model loaded",
            model=self.info.value,
            seconds=round(self.load_seconds, 2),
        )

    def unload(self) -> None:
        if not self._loaded:
            return
        self._unload()
        self._loaded = False
        gc.collect()
        self._free_device_memory()

    @abstractmethod
    def _load(self) -> None: ...

    @abstractmethod
    def _unload(self) -> None: ...

    def _free_device_memory(self) -> None:
        """Backends override to release accelerator caches after `unload`."""

    def __enter__(self) -> Self:
        self.load()
        return self

    def __exit__(self, *exc) -> None:
        self.unload()


class Transcriber(BaseParserModel):
    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe mono float32 audio; English or Ukrainian, auto-detected."""


class FrameReader(BaseParserModel):
    @abstractmethod
    def read_frame(self, image: Image.Image) -> str:
        """Return the visible text of one frame (may be empty)."""

    def read(self, frames: list[Image.Image]) -> list[str]:
        return [self.read_frame(frame) for frame in frames]


class TextGenerator(BaseParserModel):
    @abstractmethod
    def generate(self, messages: list[Message], max_new_tokens: int) -> str:
        """Greedy chat completion for system/user/assistant `messages`."""
