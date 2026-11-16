"""Caption first, then audio + on-screen text, merged by one SLM run.

Stage functions take already-built models so the benchmark can load one model at a time;
`RecipePipeline` chains them for a single reel.
"""

import re
from pathlib import Path
from time import perf_counter

from src.recipe_parser.backends.base import FrameReader, TextGenerator, Transcriber
from src.recipe_parser.heuristics import caption_signal
from src.recipe_parser.json_output import RecipeOutputError, parse_recipe
from src.recipe_parser.prompts import (
    Message,
    caption_messages,
    combine_messages,
    retry_messages,
)
from src.recipe_parser.schemas import Attempt, Evidence, ParseResult, SlmRun
from src.utils.audio import SPEECH_SAMPLE_RATE, load_audio
from src.utils.logs import Logger, LoggerMixin
from src.utils.video import sample_keyframes

MAX_JSON_ATTEMPTS = 3
SLM_MAX_NEW_TOKENS = 2048
KEYFRAME_FPS = 1.0
MAX_KEYFRAMES = 60

_SPACE_RE = re.compile(r"\s+")


def run_slm(generator: TextGenerator, messages: list[Message]) -> SlmRun:
    """Generate and validate, feeding each JSON error back for up to `MAX_JSON_ATTEMPTS`."""
    run = SlmRun()
    started = perf_counter()
    for _ in range(MAX_JSON_ATTEMPTS):
        attempt_started = perf_counter()
        raw = generator.generate(messages, SLM_MAX_NEW_TOKENS)
        seconds = perf_counter() - attempt_started
        try:
            run.recipe = parse_recipe(raw)
        except RecipeOutputError as exc:
            run.attempts.append(
                Attempt(
                    raw_output=raw,
                    error_kind=exc.kind,
                    error=str(exc),
                    seconds=seconds,
                )
            )
            Logger.warning(
                event="[run_slm]",
                msg="Rejected SLM output",
                model=generator.info.value,
                kind=exc.kind,
                error=str(exc),
            )
            messages = retry_messages(
                messages,
                raw,
                str(exc),
            )
            continue
        run.attempts.append(Attempt(raw_output=raw, seconds=seconds))
        break
    run.seconds = perf_counter() - started
    return run


def parse_caption(generator: TextGenerator, caption: str | None) -> SlmRun | None:
    """None when the heuristic gate says the caption holds no recipe (no SLM call)."""
    if not caption_signal(caption).passed:
        return None
    return run_slm(generator, caption_messages(caption))


def transcribe_video(transcriber: Transcriber, video: Path) -> tuple[str, float]:
    started = perf_counter()
    text = transcriber.transcribe(
        load_audio(video, SPEECH_SAMPLE_RATE),
        SPEECH_SAMPLE_RATE,
    )
    return text, perf_counter() - started


def dedupe_lines(blocks: list[str]) -> list[str]:
    """Split OCR blocks into lines and keep the first occurrence of each (whitespace/case-folded)."""
    seen: set[str] = set()
    lines: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            line = line.strip()
            key = _SPACE_RE.sub(" ", line).casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            lines.append(line)
    return lines


def read_screen(reader: FrameReader, video: Path) -> tuple[list[str], float]:
    started = perf_counter()
    frames = sample_keyframes(
        video,
        fps=KEYFRAME_FPS,
        max_frames=MAX_KEYFRAMES,
    )
    lines = dedupe_lines(reader.read(frames))
    return lines, perf_counter() - started


def combine(generator: TextGenerator, evidence: Evidence) -> SlmRun:
    return run_slm(generator, combine_messages(evidence))


class RecipePipeline(LoggerMixin):
    """One reel end to end. Models are loaded lazily and kept; callers own `unload()`."""

    def __init__(
        self,
        transcriber: Transcriber,
        reader: FrameReader,
        generator: TextGenerator,
    ):
        self.transcriber = transcriber
        self.reader = reader
        self.generator = generator

    @property
    def model_names(self) -> dict[str, str]:
        return {
            "asr": self.transcriber.info.value,
            "ocr": self.reader.info.value,
            "slm": self.generator.info.value,
        }

    def parse(
        self,
        video: Path,
        caption: str | None,
        *,
        force_av: bool = False,
    ) -> ParseResult:
        evidence = Evidence(caption=caption or "")
        stage_seconds: dict[str, float] = {}

        caption_run = parse_caption(self.generator, caption)
        if caption_run is not None:
            stage_seconds["caption"] = caption_run.seconds
            if caption_run.recipe is not None and caption_run.recipe.is_complete() and not force_av:
                self.log_info("Recipe taken from caption", video=str(video))
                return ParseResult(
                    recipe=caption_run.recipe,
                    path="caption",
                    evidence=evidence,
                    caption_run=caption_run,
                    stage_seconds=stage_seconds,
                    models=self.model_names,
                )

        evidence.transcript, stage_seconds["asr"] = transcribe_video(
            self.transcriber,
            video,
        )
        evidence.overlay_text, stage_seconds["ocr"] = read_screen(self.reader, video)
        combine_run = combine(self.generator, evidence)
        stage_seconds["combine"] = combine_run.seconds
        caption_complete = caption_run is not None and caption_run.recipe is not None
        caption_complete = caption_complete and caption_run.recipe.is_complete()
        return ParseResult(
            recipe=caption_run.recipe if caption_complete else combine_run.recipe,
            path="caption" if caption_complete else "av",
            evidence=evidence,
            caption_run=caption_run,
            combine_run=combine_run,
            stage_seconds=stage_seconds,
            models=self.model_names,
        )

    def unload(self) -> None:
        for model in (self.transcriber, self.reader, self.generator):
            model.unload()
