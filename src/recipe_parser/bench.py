"""Benchmark runner: compare ASR/OCR/SLM combinations on prepared reels.

Layout under `RECIPES_TEMP_DIR_PATH`:
- `media/<shortcode>/{video.mp4, caption.txt, meta.json}` — written by `prepare_reel`
- `cache/{asr,ocr}/<model slug>/<shortcode>.json` — stage outputs reused across runs
- `runs/<UTC timestamp>/` — `results.jsonl`, `summary.csv`, `judge/<shortcode>.md`

Runs are stage-major so exactly one model is in memory at a time.
"""

import csv
import json
import shutil
import statistics
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import get_context
from pathlib import Path

import aiohttp
from pydantic import BaseModel

from src.link_scrapers.scrapers.instagram_common import download_reel, extract_shortcode
from src.link_scrapers.scrapers.instagram_html import fetch_reel
from src.recipe_parser.factory import get_frame_reader, get_text_generator, get_transcriber
from src.recipe_parser.models import ParserModelsEnum
from src.recipe_parser.pipeline import combine, parse_caption, read_screen, transcribe_video
from src.recipe_parser.schemas import Evidence, ParsePath, Recipe, SlmRun
from src.settings import main_settings
from src.utils.logs import Logger
from src.utils.order import get_datetime_utc

M = ParserModelsEnum


@dataclass(frozen=True)
class PipelineConfig:
    asr: ParserModelsEnum
    ocr: ParserModelsEnum
    slm: ParserModelsEnum

    def models(self) -> tuple[ParserModelsEnum, ...]:
        return self.asr, self.ocr, self.slm


PIPELINES: dict[str, PipelineConfig] = {
    "hf-qwen": PipelineConfig(
        M.HF_WHISPER_TURBO,
        M.HF_PADDLEOCR_VL,
        M.HF_QWEN35_4B,
    ),
    "hf-gemma": PipelineConfig(
        M.HF_WHISPER_TURBO,
        M.HF_QWEN35_2B_OCR,
        M.HF_GEMMA4_E4B,
    ),
    # Same ASR + OCR as hf-gemma, so only the SLM differs between these and hf-gemma
    "hf-qwen-q2ocr": PipelineConfig(
        M.HF_WHISPER_TURBO,
        M.HF_QWEN35_2B_OCR,
        M.HF_QWEN35_4B,
    ),
    "gguf-qwen9b": PipelineConfig(
        M.HF_WHISPER_TURBO,
        M.HF_QWEN35_2B_OCR,
        M.GGUF_QWEN35_9B,
    ),
    "gguf-qwen27b": PipelineConfig(
        M.HF_WHISPER_TURBO,
        M.HF_QWEN35_2B_OCR,
        M.GGUF_QWEN35_27B,
    ),
    "gguf-qwen35b": PipelineConfig(
        M.HF_WHISPER_TURBO,
        M.HF_QWEN35_2B_OCR,
        M.GGUF_QWEN35_35B_A3B,
    ),
    "gguf-gemma12b": PipelineConfig(
        M.HF_WHISPER_TURBO,
        M.HF_QWEN35_2B_OCR,
        M.GGUF_GEMMA4_12B,
    ),
    "gguf-gemma26b": PipelineConfig(
        M.HF_WHISPER_TURBO,
        M.HF_QWEN35_2B_OCR,
        M.GGUF_GEMMA4_26B_A4B,
    ),
    "mlx-qwen9b": PipelineConfig(
        M.MLX_WHISPER_TURBO,
        M.MLX_PADDLEOCR_VL,
        M.MLX_QWEN35_9B,
    ),
    "mlx-gemma": PipelineConfig(
        M.MLX_WHISPER_LARGE,
        M.MLX_QWEN35_4B_OCR,
        M.MLX_GEMMA4_E4B,
    ),
}


# ---- media -------------------------------------------------------------------------------


def media_dir(shortcode: str) -> Path:
    return main_settings.RECIPES_TEMP_DIR_PATH / "media" / shortcode


@dataclass
class Reel:
    shortcode: str
    url: str
    video: Path
    caption: str


def read_urls(path: Path) -> list[str]:
    lines = (line.strip() for line in path.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


async def prepare_reel(url: str, session: aiohttp.ClientSession) -> Reel:
    """Return a cached reel; otherwise reuse a `cli.instagram_html` download or scrape it.

    Downloads are never deleted, so each reel hits Instagram at most once.
    """
    shortcode = extract_shortcode(url)
    cached = load_reel(shortcode)
    if cached is not None:
        return cached
    directory = media_dir(shortcode)
    meta = {"url": url, "shortcode": shortcode, "username": None}
    if not _reuse_instagram_download(shortcode, directory):
        data = await fetch_reel(url, session=session)
        if not data.video_url:
            raise ValueError(f"{shortcode} has no video")
        await download_reel(
            data,
            directory,
            session,
        )
        meta["username"] = data.username
    (directory / "meta.json").write_text(json.dumps(meta, indent=2))
    return load_reel(shortcode)


def _reuse_instagram_download(shortcode: str, directory: Path) -> bool:
    """Copy `INSTAGRAM_TEMP_DIR_PATH/<shortcode>/{video.mp4,caption.txt}` if both exist."""
    source = main_settings.INSTAGRAM_TEMP_DIR_PATH / shortcode
    names = ("video.mp4", "caption.txt")
    if not all((source / n).exists() for n in names):
        return False
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(source / name, directory / name)
    Logger.info(
        event="[bench]",
        msg="reused instagram download",
        reel=shortcode,
        source=str(source),
    )
    return True


def load_reel(shortcode: str) -> Reel | None:
    directory = media_dir(shortcode)
    video, caption, meta = (directory / n for n in ("video.mp4", "caption.txt", "meta.json"))
    if not (video.exists() and caption.exists() and meta.exists()):
        return None
    return Reel(
        shortcode=shortcode,
        url=json.loads(meta.read_text())["url"],
        video=video,
        caption=caption.read_text(),
    )


# ---- stage cache -------------------------------------------------------------------------


def _cache_path(
    stage: str,
    model: ParserModelsEnum,
    shortcode: str,
) -> Path:
    return main_settings.RECIPES_TEMP_DIR_PATH / "cache" / stage / model.value / f"{shortcode}.json"


def _read_cache(
    stage: str,
    model: ParserModelsEnum,
    shortcode: str,
) -> dict | None:
    path = _cache_path(
        stage,
        model,
        shortcode,
    )
    return json.loads(path.read_text()) if path.exists() else None


def _write_cache(
    stage: str,
    model: ParserModelsEnum,
    shortcode: str,
    payload: dict,
) -> None:
    path = _cache_path(
        stage,
        model,
        shortcode,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )


# ---- run ---------------------------------------------------------------------------------


class ReelResult(BaseModel):
    pipeline: str
    shortcode: str
    url: str
    path: ParsePath
    recipe: Recipe | None
    caption_gate: bool
    caption_run: SlmRun | None
    combine_run: SlmRun
    evidence: Evidence
    stage_seconds: dict[str, float]
    pipeline_seconds: float

    @property
    def runs(self) -> list[SlmRun]:
        return [r for r in (self.caption_run, self.combine_run) if r is not None]


@dataclass
class BenchRun:
    results: list[ReelResult] = field(default_factory=list)
    load_seconds: dict[str, float] = field(default_factory=dict)


def _in_subprocess(worker, *args):
    """Run one model's work in a fresh spawned process.

    Isolation is required, not just tidy: importing mlx-vlm's Qwen modules patches
    transformers' `AutoProcessor` process-wide, which breaks the transformers Qwen3.5 backend.
    It also guarantees each model's memory is returned before the next one loads.
    """
    with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as pool:
        return pool.submit(worker, *args).result()


def _media_worker(
    stage: str,
    model: ParserModelsEnum,
    reels: list[Reel],
) -> float:
    """Fill the `stage` cache for `reels`; returns the model load time."""
    built = get_transcriber(model) if stage == "asr" else get_frame_reader(model)
    with built:
        for reel in reels:
            if stage == "asr":
                text, seconds = transcribe_video(built, reel.video)
                payload = {"text": text, "seconds": seconds}
            else:
                lines, seconds = read_screen(built, reel.video)
                payload = {"lines": lines, "seconds": seconds}
            _write_cache(
                stage,
                model,
                reel.shortcode,
                payload,
            )
            Logger.info(
                event="[bench]",
                msg=f"{stage} done",
                model=model.value,
                reel=reel.shortcode,
            )
        return built.load_seconds


SlmOutputs = list[tuple[str, str, SlmRun | None, SlmRun]]


def _slm_worker(
    slm: ParserModelsEnum,
    users: dict[str, PipelineConfig],
    reels: list[Reel],
) -> tuple[float, SlmOutputs]:
    """Caption parse once per reel, then one combine run per pipeline using this SLM."""
    outputs: SlmOutputs = []
    with get_text_generator(slm) as generator:
        for reel in reels:
            caption_run = parse_caption(generator, reel.caption)
            for name, config in users.items():
                evidence = _evidence(reel, config)
                outputs.append(
                    (name, reel.shortcode, caption_run, combine(generator, evidence)),
                )
        return generator.load_seconds, outputs


def _evidence(reel: Reel, config: PipelineConfig) -> Evidence:
    return Evidence(
        caption=reel.caption,
        transcript=_read_cache(
            "asr",
            config.asr,
            reel.shortcode,
        )["text"],
        overlay_text=_read_cache(
            "ocr",
            config.ocr,
            reel.shortcode,
        )["lines"],
    )


def run_bench(pipeline_names: list[str], reels: list[Reel]) -> BenchRun:
    configs = {name: PIPELINES[name] for name in pipeline_names}
    bench = BenchRun()
    for stage, models in (
        ("asr", {c.asr for c in configs.values()}),
        ("ocr", {c.ocr for c in configs.values()}),
    ):
        for model in sorted(models):
            missing = [
                r
                for r in reels
                if _read_cache(
                    stage,
                    model,
                    r.shortcode,
                )
                is None
            ]
            if missing:
                bench.load_seconds[model.value] = _in_subprocess(
                    _media_worker,
                    stage,
                    model,
                    missing,
                )

    by_reel = {reel.shortcode: reel for reel in reels}
    for slm in sorted({c.slm for c in configs.values()}):
        users = {name: c for name, c in configs.items() if c.slm is slm}
        load_seconds, outputs = _in_subprocess(
            _slm_worker,
            slm,
            users,
            reels,
        )
        bench.load_seconds[slm.value] = load_seconds
        for name, shortcode, caption_run, combine_run in outputs:
            reel = by_reel[shortcode]
            bench.results.append(
                _reel_result(
                    name,
                    reel,
                    caption_run,
                    combine_run,
                    _evidence(reel, configs[name]),
                )
            )
    order = {name: i for i, name in enumerate(pipeline_names)}
    bench.results.sort(key=lambda r: (order[r.pipeline], r.shortcode))
    return bench


def _reel_result(
    name: str,
    reel: Reel,
    caption_run: SlmRun | None,
    combine_run: SlmRun,
    evidence: Evidence,
) -> ReelResult:
    """Apply the production rule: a complete caption recipe wins and skips the av stages."""
    config = PIPELINES[name]
    stage_seconds = {
        "asr": _read_cache(
            "asr",
            config.asr,
            reel.shortcode,
        )["seconds"],
        "ocr": _read_cache(
            "ocr",
            config.ocr,
            reel.shortcode,
        )["seconds"],
        "combine": combine_run.seconds,
    }
    if caption_run is not None:
        stage_seconds["caption"] = caption_run.seconds
    caption_ok = caption_run is not None and caption_run.recipe is not None
    caption_ok = caption_ok and caption_run.recipe.is_complete()
    pipeline_seconds = stage_seconds["caption"] if caption_ok else sum(stage_seconds.values())
    return ReelResult(
        pipeline=name,
        shortcode=reel.shortcode,
        url=reel.url,
        path="caption" if caption_ok else "av",
        recipe=caption_run.recipe if caption_ok else combine_run.recipe,
        caption_gate=caption_run is not None,
        caption_run=caption_run,
        combine_run=combine_run,
        evidence=evidence,
        stage_seconds=stage_seconds,
        pipeline_seconds=pipeline_seconds,
    )


# ---- reports -----------------------------------------------------------------------------


def write_reports(bench: BenchRun, pipeline_names: list[str]) -> Path:
    run_dir = (
        main_settings.RECIPES_TEMP_DIR_PATH / "runs" / get_datetime_utc().strftime("%Y%m%dT%H%M%SZ")
    )
    (run_dir / "judge").mkdir(parents=True)
    with (run_dir / "results.jsonl").open("w") as f:
        for result in bench.results:
            f.write(result.model_dump_json() + "\n")
    _write_summary(
        run_dir / "summary.csv",
        bench,
        pipeline_names,
    )
    _write_judge(run_dir / "judge", bench)
    (run_dir / "pipelines.json").write_text(
        json.dumps(
            {n: [m.value for m in PIPELINES[n].models()] for n in pipeline_names},
            indent=2,
        )
    )
    return run_dir


def _stats(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    return statistics.fmean(values), statistics.median(values), max(values)


def summarize(bench: BenchRun, pipeline_names: list[str]) -> list[dict]:
    rows = []
    for name in pipeline_names:
        results = [r for r in bench.results if r.pipeline == name]
        attempts = [a for r in results for run in r.runs for a in run.attempts]
        mean, p50, peak = _stats([r.pipeline_seconds for r in results])
        row = {
            "pipeline": name,
            "reels": len(results),
            "caption_path": sum(r.path == "caption" for r in results),
            "av_path": sum(r.path == "av" for r in results),
            "final_failures": sum(r.recipe is None for r in results),
            "slm_attempts": len(attempts),
            "json_errors": sum(a.error_kind is not None for a in attempts),
            "parse_errors": sum(a.error_kind == "parse" for a in attempts),
            "validation_errors": sum(a.error_kind == "validation" for a in attempts),
            "reel_s_mean": round(mean, 2),
            "reel_s_p50": round(p50, 2),
            "reel_s_max": round(peak, 2),
        }
        for stage in ("caption", "asr", "ocr", "combine"):
            values = [r.stage_seconds[stage] for r in results if stage in r.stage_seconds]
            row[f"{stage}_s_mean"] = round(_stats(values)[0], 2)
        loads = [bench.load_seconds.get(m.value) for m in PIPELINES[name].models()]
        row["load_s"] = round(sum(s for s in loads if s is not None), 2)
        rows.append(row)
    return rows


def _write_summary(
    path: Path,
    bench: BenchRun,
    pipeline_names: list[str],
) -> None:
    rows = summarize(bench, pipeline_names)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_judge(directory: Path, bench: BenchRun) -> None:
    """One markdown per reel: shared evidence, then every pipeline's final recipe."""
    by_reel: dict[str, list[ReelResult]] = {}
    for result in bench.results:
        by_reel.setdefault(result.shortcode, []).append(result)
    for shortcode, results in by_reel.items():
        first = results[0]
        parts = [
            f"# {shortcode}",
            f"URL: {first.url}",
            "## Description",
            first.evidence.caption.strip() or "(empty)",
        ]
        transcripts = {PIPELINES[r.pipeline].asr: r.evidence.transcript for r in results}
        overlays = {PIPELINES[r.pipeline].ocr: r.evidence.overlay_text for r in results}
        for model, text in transcripts.items():
            parts += [f"## Transcript ({model.value})", text or "(empty)"]
        for model, lines in overlays.items():
            parts += [
                f"## On-screen text ({model.value})",
                "\n".join(lines) or "(empty)",
            ]
        for result in results:
            recipe = result.recipe.model_dump_json(indent=2) if result.recipe else "null"
            errors = sum(run.json_errors for run in result.runs)
            parts += [
                f"## Recipe from `{result.pipeline}` (path={result.path}, json_errors={errors}, "
                f"{result.pipeline_seconds:.1f}s)",
                f"```json\n{recipe}\n```",
            ]
        (directory / f"{shortcode}.md").write_text("\n\n".join(parts) + "\n")
