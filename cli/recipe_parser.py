"""Parse one cooking reel into a recipe JSON with `src.recipe_parser.pipeline.RecipePipeline`.

Run with:

    uv run python -m cli.recipe_parser <reel-url | shortcode | video.mp4> \
        [--caption-file caption.txt] [--pipeline hf-qwen] [--asr ... --ocr ... --slm ...] [--force-av]
        [--out result.json]

A url/shortcode is prepared into `temp/recipes/media/<shortcode>` first (cached). Prints the
full `ParseResult` JSON; exits 1 when no recipe could be produced.
"""

import argparse
import asyncio
from pathlib import Path

import aiohttp

from src.recipe_parser.bench import PIPELINES, Reel, prepare_reel
from src.recipe_parser.factory import get_frame_reader, get_text_generator, get_transcriber
from src.recipe_parser.models import ParserModelsEnum
from src.recipe_parser.pipeline import RecipePipeline


async def _resolve(target: str) -> Reel:
    path = Path(target)
    if path.exists():
        return Reel(
            shortcode=path.stem,
            url=str(path),
            video=path,
            caption="",
        )
    async with aiohttp.ClientSession() as session:
        return await prepare_reel(target, session)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("target", help="Reel url, shortcode or local video path")
    parser.add_argument(
        "--caption-file",
        type=Path,
        help="Caption for a local video",
    )
    parser.add_argument(
        "--pipeline",
        default="hf-qwen",
        choices=list(PIPELINES),
    )
    choices = [m.value for m in ParserModelsEnum]
    for role in ("asr", "ocr", "slm"):
        parser.add_argument(
            f"--{role}",
            choices=choices,
            help=f"Override the pipeline's {role} model",
        )
    parser.add_argument(
        "--out",
        type=Path,
        help="Also write the ParseResult JSON here (stdout carries log lines too)",
    )
    parser.add_argument(
        "--force-av",
        action="store_true",
        help="Run audio+OCR even after a caption hit",
    )
    args = parser.parse_args()

    reel = asyncio.run(_resolve(args.target))
    caption = args.caption_file.read_text() if args.caption_file else reel.caption
    config = PIPELINES[args.pipeline]
    pipeline = RecipePipeline(
        get_transcriber(ParserModelsEnum(args.asr) if args.asr else config.asr),
        get_frame_reader(ParserModelsEnum(args.ocr) if args.ocr else config.ocr),
        get_text_generator(ParserModelsEnum(args.slm) if args.slm else config.slm),
    )
    try:
        result = pipeline.parse(
            reel.video,
            caption,
            force_av=args.force_av,
        )
    finally:
        pipeline.unload()
    payload = result.model_dump_json(indent=2)
    print(payload)
    if args.out:
        args.out.write_text(payload)
        print(f"Saved ParseResult to {args.out}")
    return 0 if result.recipe is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
