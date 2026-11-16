# Recipe parser + model benchmark: Handoff

*Date: 2026-11-16 · Purpose: continue building/benchmarking the cooking-reel → recipe JSON module in Octo · Plan: `~/.claude/plans/let-s-focus-on-such-binary-waffle.md`*

> **Instagram scraper fixed (2026-11-16): next, run `cli.recipe_bench prepare`.** GraphQL is still blocked with 401 (`Please wait a few minutes…`), so `bench.prepare_reel`, `LinkScraper` and `cli.recipe_parser` now use the new HTML scraper `src/link_scrapers/scrapers/instagram_html.py`. It parses the logged-out permalink page and falls back to the embed page; no cookies, tokens or GraphQL. All 4 test reels parse, including one whose video was downloaded live. `prepare` itself has not been run yet. The shared Instagram limiters allow 1 request per 60 s, so preparing 4 reels takes about 4 minutes.

## 1. Where things stand

| Area | State |
|---|---|
| `src/recipe_parser/` package (schemas, heuristics, prompts, JSON validation, registry, HF + MLX backends, pipeline, bench) | Written, ruff-clean, imports fine |
| `cli/recipe_bench.py` (`prepare` / `download-models` / `run` / `list`), `cli/recipe_parser.py` | Written |
| `src/utils/audio.py` `load_audio`, `src/utils/video.py` `sample_keyframes` | Verified on `temp/instagram/test.mp4`: 25.6 s audio decoded in 0.06 s; 26 keyframes in 0.23 s |
| All 11 model weights | Downloaded to `models/` (HF cache layout, ~53 GB total in `models/`) |
| ASR + OCR stages, all 7 models (3 Whisper, 4 OCR) | Ran successfully on the staged test video; outputs cached in `temp/recipes/cache/{asr,ocr}/<slug>/test.json` |
| `mlx-gemma` pipeline end to end (`cli.recipe_parser ... --force-av`) | Worked: valid JSON on first attempt; asr 4.8 s, ocr 58.0 s, combine 42.8 s |
| SLM stage in `run` | First run crashed on `hf-qwen3.5-4b` (MLX processor patch, see Gotchas). Fixed with per-model subprocesses; the re-run was stopped by the user, so **subprocess isolation is untested** |
| Instagram scraping for the bench | **Fixed** with the HTML scraper (`instagram_html.fetch_reel`). Captions, video URLs and the `video.mp4` download are verified on the test reels |
| Benchmark on real reels | **Not done**: unblocked, waiting on `prepare` |

**Test data caveat (user):** `temp/instagram/test.mp4` (staged as `temp/recipes/media/test/` with an empty `caption.txt`) has only visuals (an app ad that scrolls through a recipe on screen, with a music track), and no speech or caption. It is **not suitable** for this benchmark; use it only as a smoke test. Delete `temp/recipes/media/test/` and `temp/recipes/cache/*/*/test.json` before the real runs.

## 2. Key facts

| Fact | Status |
|---|---|
| Machine: Apple M5, 24 GB RAM; torch 2.13, transformers 5.20, sentence-transformers 6.1 | Measured |
| mlx 0.32.4, mlx-lm 0.32.2, mlx-vlm 0.7.12, mlx-whisper 0.4.3 resolve alongside transformers 5.20; torchcodec still not installed | Verified (`uv add --group mlx`) |
| Qwen3-ASR (transformers native) has no Ukrainian in `LANGUAGE_CODE_TO_NAME` | Verified in source |
| Qwen3.5 chat template has thinking on by default; `enable_thinking=False` adds an empty think block | Verified in template |
| Gemma 4, Qwen3.5 and PaddleOCR-VL all load via `AutoModelForImageTextToText` | Verified in `modeling_auto.py` |
| PaddleOCR-VL task prompt is `OCR:` | From model card |
| Test set: `cli/seed_urls_recipies.txt`, 4 reels (Dfkc1b-ofqG, Ddot2x-IGIO, DcqUwgqugH2, DflKar5OotU), the recipe sits in the description, audio or on-screen text | Given by user |
| Smoke-test OCR quality: on-screen recipe captured (steps, 350°F/175°C); SLM attached "300 ml" to chicken breast instead of buttermilk | Observed, 1 sample |
| `hf-gemma-4-e4b` combine on the test video: 2 rejected attempts, both `invalid JSON: Expecting ',' delimiter: line 1 column 2020` | Observed; raw outputs lost in the crash, cause not inspected (possible truncation at `SLM_MAX_NEW_TOKENS=2048`, or the retry not changing the output) |

## 3. Decisions

- **Flow (user):** description first → if the heuristic gate passes, the SLM parses it; a "complete" recipe (≥3 ingredients, ≥1 step) returns `path="caption"` and skips the rest. Otherwise Whisper + keyframe OCR + description feed one combine SLM run, with up to 3 JSON attempts and the error fed back. **Quantities are optional and never a failure reason** (user).
- **Languages (user):** input English or Ukrainian, **never Russian**; the recipe output is **always English**. Recorded in root `AGENTS.md` → User Preferences.
- **Metrics:** time per stage plus JSON failures (parse vs validation, retries, final failures). **Content accuracy is scored later by the user with an LLM judge (no API)**, from `judge/<shortcode>.md`.
- **No constrained decoding / JSON repair**, so JSON failures stay meaningful as a metric.
- **Runtimes (user):** both transformers and MLX. The `mlx` dependency group has darwin markers and is listed in `[tool.uv] default-groups = ["dev", "mlx"]`, so `uv sync` keeps it and Docker (Linux) installs nothing from it.
- **ASR is Whisper only**: Qwen3-ASR was rejected because it has no Ukrainian. Language detection is restricted to `en`/`uk` (Cyrillic look-alikes map to `uk`).
- **Benchmark is stage-major** with each model in its own spawned subprocess; ASR/OCR outputs are cached per model and reused across pipelines and runs.
- Not wired into the API or `OmniPipeline` yet (bench first).

Pipelines (`src/recipe_parser/bench.py` → `PIPELINES`):

| Name | ASR | OCR | SLM |
|---|---|---|---|
| `hf-qwen` | openai/whisper-large-v3-turbo | PaddlePaddle/PaddleOCR-VL-1.5 | Qwen/Qwen3.5-4B (bf16 on MPS) |
| `hf-gemma` | openai/whisper-large-v3-turbo | Qwen/Qwen3.5-2B (OCR prompt) | google/gemma-4-E4B-it |
| `mlx-qwen9b` | mlx-community/whisper-large-v3-turbo | mlx-community/PaddleOCR-VL-1.5-8bit | mlx-community/Qwen3.5-9B-4bit |
| `mlx-gemma` | mlx-community/whisper-large-v3-mlx | mlx-community/Qwen3.5-4B-MLX-4bit | mlx-community/gemma-4-e4b-it-4bit |

## 4. Commands

```bash
uv run python -m cli.recipe_bench list
uv run python -m cli.recipe_bench prepare                 # default --file cli/seed_urls_recipies.txt; aborts on ScraperStatusError
uv run python -m cli.recipe_bench download-models         # already done
uv run python -m cli.recipe_bench run [--pipelines hf-qwen,mlx-gemma] [--limit N]
uv run python -m cli.recipe_parser <reel-url|shortcode|video.mp4> [--caption-file f] [--pipeline mlx-gemma] [--asr/--ocr/--slm <slug>] [--force-av] [--out result.json]
pyfmt <only the files you changed>                        # see Gotchas
```

Outputs: `temp/recipes/media/<shortcode>/{video.mp4,caption.txt,meta.json}`, `temp/recipes/cache/{asr,ocr}/<slug>/<shortcode>.json`, `temp/recipes/runs/<UTC>/{results.jsonl,summary.csv,pipelines.json,judge/<shortcode>.md}`.

## 5. Gotchas

- **mlx-vlm patches transformers globally**: importing its `qwen3_vl` module calls `install_auto_processor_patch`, after which `AutoProcessor.from_pretrained("Qwen/Qwen3.5-4B")` returns an MLX processor and `generate` fails with `'mlx.core.array' object has no attribute 'device'`. Fixes: `bench._in_subprocess` (spawn, one model per process) and a guard in `HfChatModel._load` that raises if the processor module starts with `mlx_vlm`. `cli.recipe_parser` still loads all three models in one process, so **don't mix an MLX Qwen OCR model with an HF Qwen SLM there**.
- **Logs share stdout**: structlog writes to stdout, so `cli.recipe_parser > file.json` is not valid JSON. Use `--out`.
- **pyfmt reformats the whole tree**: `pyfmt src alembic cli` also rewrote ~20 unrelated files (comma rule on existing code). Reverting them was blocked by the permission check, so they are **still modified** (`src/api`, `src/db`, `src/embedders`, `src/services`, `cli/{nvidia_cosmos,postgres,qdrant_backfill,seeder,youtube}.py`, plus part of `src/link_scrapers`). Decide whether to keep or `git checkout --` them. pyfmt runs on Python 3.11, so PEP 695 syntax (`def f[T]()`) breaks it.
- **Instagram scraper layout**:
  - `instagram_common.py` holds `ReelData` (now with a `source` field), `InstagramFetchError`, `extract_shortcode` and `download_reel`. `download_reel` writes `video.mp4` + `caption.txt`.
  - `instagram_html.py` is the live scraper. `instagram_graphql.py` is standalone, reached only through `cli.instagram_graphql`.
  - `bench.prepare_reel` already calls `instagram_html.fetch_reel` + `download_reel`.
  - Details: `src/link_scrapers/AGENTS.md` and `scrapers-knowledge/instagram-knowledge.md`.
- **Instagram limits**:
  - The 1 request per 60 s and 60 per hour limiters are self-imposed. Instagram's own threshold for page requests has not been measured.
  - A login-page redirect or a 429 raises `ScraperStatusError`, and `prepare` aborts on it.
  - A login page served with a plain 200 would show up as per-post "no post data" errors instead. Detecting that case was proposed but not added.
- **Comments are not scraped.** Logged-out pages embed only the ~10–12 newest comments, and the comments API redirects to the login page. An author's pinned recipe comment is therefore unreachable without login, so recipes must come from the description, audio or on-screen text.
- **Keyframe dedup kept all 26 of 26 frames** on the test clip (`diff_threshold=6.0`). OCR cost scales with frame count (~58 s for 26 frames with MLX Qwen3.5-4B), so tune `sample_keyframes(diff_threshold=)`, `KEYFRAME_FPS` and `MAX_KEYFRAMES` from real results.
- Whisper returned an empty transcript for the music-only test clip, which is expected (no speech).

## 6. Next steps

- [x] Fix the Instagram scraper 401 block (HTML scraper, see Gotchas)
- [x] Switch `bench.prepare_reel` to `download_reel`
- [ ] `uv run python -m cli.recipe_bench prepare` for the 4 reels in `cli/seed_urls_recipies.txt` (~4 min because of the limiter)
- [ ] Remove the staged smoke-test reel: `temp/recipes/media/test/` and `temp/recipes/cache/*/*/test.json`
- [ ] Optional: treat a 200 login-wall page as `ScraperStatusError` in `instagram_html`; decide on the limiter (keep 1 per 60 s, or 1 per 30 s / lower hourly cap)
- [ ] Run `cli.recipe_bench run` on all 4 pipelines; confirm subprocess isolation works for `hf-qwen` after MLX models
- [ ] Inspect `hf-gemma-4-e4b` JSON failures in `results.jsonl` (truncation vs. retry repeating itself); raise `SLM_MAX_NEW_TOKENS` or adjust the retry prompt if needed
- [ ] Check that the description reel takes `path="caption"` and the audio/visual reels take `path="av"`, and that all recipes are in English
- [ ] User: score `judge/*.md` with an LLM judge
- [ ] Tune the gate threshold and keyframe parameters from results
- [ ] Decide on the pyfmt-reformatted unrelated files
- [ ] Later: wire the winning pipeline into the API / `OmniPipeline`

*Sources: tool output from this session (installs, source inspection, smoke runs, scraper errors, 2026-11-16 Instagram HTML-scraper probes and live runs); user statements (flow, languages, metrics, runtimes, test set, test-video unsuitability). Model choice rationale comes from web research (secondary sources); per-model quality on real reels is not measured yet.*
