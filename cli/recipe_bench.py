"""Benchmark recipe-parsing pipelines (ASR + OCR + SLM combinations) on cooking reels.

Run with:

    uv run python -m cli.recipe_bench prepare [--file cli/seed_urls_recipies.txt]
    uv run python -m cli.recipe_bench download-models [--pipelines hf-qwen,mlx-gemma]
    uv run python -m cli.recipe_bench run [--pipelines ...] [--limit N]
    uv run python -m cli.recipe_bench list

`run` writes `temp/recipes/runs/<UTC timestamp>/` (results.jsonl, summary.csv, judge/*.md).
"""

import argparse
import asyncio
from pathlib import Path

import aiohttp

from src.link_scrapers.errors import ScraperStatusError
from src.link_scrapers.scrapers.instagram_common import extract_shortcode
from src.recipe_parser.bench import (
    PIPELINES,
    load_reel,
    prepare_reel,
    read_urls,
    run_bench,
    summarize,
    write_reports,
)
from src.recipe_parser.factory import get_parser_model

DEFAULT_URLS = Path(__file__).parent / "seed_urls_recipies.txt"


def _pipelines(value: str | None) -> list[str]:
    names = [n.strip() for n in value.split(",")] if value else list(PIPELINES)
    unknown = [n for n in names if n not in PIPELINES]
    if unknown:
        raise SystemExit(f"Unknown pipelines {unknown}; choose from {list(PIPELINES)}")
    return names


async def _prepare(urls: list[str]) -> int:
    failures = 0
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                reel = await prepare_reel(url, session)
            except ScraperStatusError as exc:
                print(
                    f"ABORTED at {url}: {exc} (Instagram is refusing requests; retry later)",
                )
                return 1
            except Exception as exc:
                failures += 1
                print(f"FAILED {url}: {type(exc).__name__}: {exc}")
                continue
            print(
                f"ok {reel.shortcode}: {len(reel.caption)} caption chars -> {reel.video}",
            )
    return 1 if failures else 0


def _download(names: list[str]) -> int:
    for model in sorted({m for n in names for m in PIPELINES[n].models()}):
        path = get_parser_model(model).download()
        print(f"ok {model.value} -> {path}")
    return 0


def _run(
    names: list[str],
    urls: list[str],
    limit: int | None,
) -> int:
    reels = []
    for url in urls:
        reel = load_reel(extract_shortcode(url))
        if reel is None:
            print(f"skip {url}: not prepared (run `prepare` first)")
            continue
        reels.append(reel)
    reels = reels[:limit] if limit else reels
    if not reels:
        print("No prepared reels")
        return 1

    bench = run_bench(names, reels)
    run_dir = write_reports(bench, names)
    for row in summarize(bench, names):
        print(
            f"{row['pipeline']:<12} reels={row['reels']} caption={row['caption_path']} "
            f"av={row['av_path']} failed={row['final_failures']} json_errors={row['json_errors']} "
            f"(parse={row['parse_errors']}, validation={row['validation_errors']}) "
            f"reel_s mean={row['reel_s_mean']} max={row['reel_s_max']} load_s={row['load_s']}"
        )
    print(f"Reports in {run_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser(
        "prepare",
        help="scrape + download reels into temp/recipes/media",
    )
    prepare.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_URLS,
    )
    download = sub.add_parser(
        "download-models",
        help="fetch weights so timings exclude downloads",
    )
    download.add_argument("--pipelines")
    run = sub.add_parser("run", help="benchmark pipelines on prepared reels")
    run.add_argument("--pipelines")
    run.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_URLS,
    )
    run.add_argument("--limit", type=int)
    sub.add_parser("list", help="print the pipeline definitions")
    args = parser.parse_args()

    if args.command == "prepare":
        return asyncio.run(_prepare(read_urls(args.file)))
    if args.command == "download-models":
        return _download(_pipelines(args.pipelines))
    if args.command == "run":
        return _run(
            _pipelines(args.pipelines),
            read_urls(args.file),
            args.limit,
        )
    for name, config in PIPELINES.items():
        print(f"{name:<12} " + "  ".join(m.value for m in config.models()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
