from src.recipe_parser.backends.base import BaseParserModel, FrameReader, TextGenerator, Transcriber
from src.recipe_parser.backends.hf import HfChatModel, HfWhisperTranscriber
from src.recipe_parser.backends.mlx import MlxFrameReader, MlxTextGenerator, MlxWhisperTranscriber
from src.recipe_parser.models import ParserBackend, ParserModelsEnum, ParserRole

MODELS: dict[tuple[ParserRole, ParserBackend], type[BaseParserModel]] = {
    (ParserRole.ASR, "transformers"): HfWhisperTranscriber,
    (ParserRole.ASR, "mlx"): MlxWhisperTranscriber,
    (ParserRole.OCR, "transformers"): HfChatModel,
    (ParserRole.OCR, "mlx"): MlxFrameReader,
    (ParserRole.SLM, "transformers"): HfChatModel,
    (ParserRole.SLM, "mlx"): MlxTextGenerator,
}


def get_parser_model(model: ParserModelsEnum) -> BaseParserModel:
    """Build the class registered for `model`'s role and backend (not loaded yet)."""
    spec = model.get_spec()
    model_cls = MODELS.get((spec.role, spec.backend))
    if model_cls is None:
        raise ValueError(
            f"No parser model class for {spec.role}/{spec.backend} ({model.value})",
        )
    return model_cls(model)


def get_transcriber(model: ParserModelsEnum) -> Transcriber:
    built = _checked(model, ParserRole.ASR)
    assert isinstance(built, Transcriber)
    return built


def get_frame_reader(model: ParserModelsEnum) -> FrameReader:
    built = _checked(model, ParserRole.OCR)
    assert isinstance(built, FrameReader)
    return built


def get_text_generator(model: ParserModelsEnum) -> TextGenerator:
    built = _checked(model, ParserRole.SLM)
    assert isinstance(built, TextGenerator)
    return built


def _checked(model: ParserModelsEnum, role: ParserRole) -> BaseParserModel:
    if model.get_spec().role is not role:
        raise ValueError(
            f"{model.value} is a {model.get_spec().role} model, expected {role}",
        )
    return get_parser_model(model)
