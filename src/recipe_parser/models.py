from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

ParserBackend = Literal["transformers", "mlx"]


class ParserRole(StrEnum):
    ASR = "asr"
    OCR = "ocr"
    SLM = "slm"


@dataclass(frozen=True)
class ParserModelSpec:
    """`repo` is the HuggingFace repo id; `load_kwargs` go verbatim to the backend loader."""

    role: ParserRole
    backend: ParserBackend
    repo: str
    load_kwargs: dict = field(default_factory=dict)


class ParserModelsEnum(StrEnum):
    """Values are stable slugs used in cache paths, CLI flags and benchmark output."""

    # ASR: Whisper only; Qwen3-ASR has no Ukrainian.
    HF_WHISPER_TURBO = "hf-whisper-large-v3-turbo"
    MLX_WHISPER_TURBO = "mlx-whisper-large-v3-turbo"
    MLX_WHISPER_LARGE = "mlx-whisper-large-v3"
    # OCR on keyframes
    HF_PADDLEOCR_VL = "hf-paddleocr-vl-1.5"
    HF_QWEN35_2B_OCR = "hf-qwen3.5-2b-ocr"
    MLX_PADDLEOCR_VL = "mlx-paddleocr-vl-1.5-8bit"
    MLX_QWEN35_4B_OCR = "mlx-qwen3.5-4b-4bit-ocr"
    # SLM: text -> recipe JSON
    HF_QWEN35_4B = "hf-qwen3.5-4b"
    HF_GEMMA4_E4B = "hf-gemma-4-e4b"
    MLX_QWEN35_9B = "mlx-qwen3.5-9b-4bit"
    MLX_GEMMA4_E4B = "mlx-gemma-4-e4b-4bit"

    def get_spec(self) -> ParserModelSpec:
        return PARSER_MODEL_CONFIG[self]


PARSER_MODEL_CONFIG: dict[ParserModelsEnum, ParserModelSpec] = {
    ParserModelsEnum.HF_WHISPER_TURBO: ParserModelSpec(
        ParserRole.ASR,
        "transformers",
        "openai/whisper-large-v3-turbo",
    ),
    ParserModelsEnum.MLX_WHISPER_TURBO: ParserModelSpec(
        ParserRole.ASR,
        "mlx",
        "mlx-community/whisper-large-v3-turbo",
    ),
    ParserModelsEnum.MLX_WHISPER_LARGE: ParserModelSpec(
        ParserRole.ASR,
        "mlx",
        "mlx-community/whisper-large-v3-mlx",
    ),
    ParserModelsEnum.HF_PADDLEOCR_VL: ParserModelSpec(
        ParserRole.OCR,
        "transformers",
        "PaddlePaddle/PaddleOCR-VL-1.5",
    ),
    ParserModelsEnum.HF_QWEN35_2B_OCR: ParserModelSpec(
        ParserRole.OCR,
        "transformers",
        "Qwen/Qwen3.5-2B",
    ),
    ParserModelsEnum.MLX_PADDLEOCR_VL: ParserModelSpec(
        ParserRole.OCR,
        "mlx",
        "mlx-community/PaddleOCR-VL-1.5-8bit",
    ),
    ParserModelsEnum.MLX_QWEN35_4B_OCR: ParserModelSpec(
        ParserRole.OCR,
        "mlx",
        "mlx-community/Qwen3.5-4B-MLX-4bit",
    ),
    ParserModelsEnum.HF_QWEN35_4B: ParserModelSpec(
        ParserRole.SLM,
        "transformers",
        "Qwen/Qwen3.5-4B",
    ),
    ParserModelsEnum.HF_GEMMA4_E4B: ParserModelSpec(
        ParserRole.SLM,
        "transformers",
        "google/gemma-4-E4B-it",
    ),
    ParserModelsEnum.MLX_QWEN35_9B: ParserModelSpec(
        ParserRole.SLM,
        "mlx",
        "mlx-community/Qwen3.5-9B-4bit",
    ),
    ParserModelsEnum.MLX_GEMMA4_E4B: ParserModelSpec(
        ParserRole.SLM,
        "mlx",
        "mlx-community/gemma-4-e4b-it-4bit",
    ),
}

_unregistered = [m.name for m in ParserModelsEnum if m not in PARSER_MODEL_CONFIG]
if _unregistered:
    raise RuntimeError(f"ParserModelsEnum members without a spec: {_unregistered}")
