# src/recipe_parser DOX

## Purpose

- Turn a downloaded cooking reel (video + description) into a validated English `Recipe` JSON with small local models, and benchmark ASR/OCR/SLM combinations for it. Not wired into the API or `OmniPipeline` yet

## Ownership

- `schemas.py` — `Recipe` (+ `Ingredient`, `Step`, `Temperature`), `Evidence`, `Attempt`, `SlmRun`, `ParseResult`; `Recipe.is_complete()` (≥3 ingredients, ≥1 step)
- `heuristics.py` — `caption_signal`, the regex gate deciding whether the description is worth an SLM parse (`GATE_THRESHOLD`)
- `prompts.py` — system/caption/combine/retry prompts (schema embedded from `Recipe`), OCR prompts, `ASR_LANGUAGES`
- `json_output.py` — `parse_recipe` / `extract_json` and `RecipeOutputError(kind=parse|validation)`
- `models.py` — `ParserModelsEnum` (slug values) + `PARSER_MODEL_CONFIG` (`ParserModelSpec`: role, backend, repo)
- `backends/base.py` — `BaseParserModel` lifecycle, `Transcriber` / `FrameReader` / `TextGenerator`, `restrict_language`
- `backends/hf.py` — transformers: `HfWhisperTranscriber`, `HfChatModel` (any `AutoModelForImageTextToText`; OCR and SLM roles)
- `backends/mlx.py` — `MlxWhisperTranscriber`, `MlxTextGenerator` (mlx-lm), `MlxFrameReader` (mlx-vlm)
- `backends/llamacpp.py` — `LlamaCppTextGenerator`: GGUF SLMs served by a `llama-server` child process (OpenAI chat API on a free localhost port)
- `factory.py` — `get_parser_model` and the role-checked `get_transcriber` / `get_frame_reader` / `get_text_generator`
- `pipeline.py` — stage functions (`run_slm`, `parse_caption`, `transcribe_video`, `read_screen`, `combine`) and `RecipePipeline.parse`
- `bench.py` — `PIPELINES`, reel preparation/cache layout, stage-major `run_bench`, `summarize`, `write_reports`

## Local Contracts

- Flow: caption gate → SLM parses the description → a complete recipe returns with `path="caption"` and skips the rest; otherwise Whisper transcript + keyframe OCR + description go to one combine SLM run (`path="av"`). Quantities are optional and never make a recipe incomplete
- Language: input is English or Ukrainian, never Russian. Heuristics only know these two; Whisper language detection is restricted to `en`/`uk` (`restrict_language`). Every recipe value is English; transcripts and OCR lines stay in their source language
- Every SLM stage goes through `run_slm`: up to `MAX_JSON_ATTEMPTS` (3), each failure appended as an `Attempt` and fed back via the retry prompt. No constrained decoding or JSON repair: JSON failures are a benchmark metric
- Recipe models (`StrictModel`) forbid unknown keys, so a wrapped object (`{"Recipe": {...}}`) or an echoed JSON Schema is a validation error, never a silently empty recipe. The system prompt shows `RECIPE_SHAPE` (a type template), not the JSON Schema; `prompts.py` fails at import if its keys drift from `Recipe` fields
- Models are referenced only through `ParserModelsEnum`; adding one means the enum member plus its spec (import fails otherwise). Weights live in the HF cache layout under `MODELS_PATH` (`cache_dir=` / `snapshot_download(cache_dir=)`)
- Audio and frames go to models as numpy/PIL from `src.utils.audio.load_audio` and `src.utils.video.sample_keyframes`, never as paths: torchcodec stays uninstalled
- HF generative models run in bfloat16 on MPS and CUDA (`generation_device`); chat templates get `enable_thinking=False` and `<think>` blocks are stripped anyway
- On CUDA, `ParserModelSpec.cpu_modules` stay on CPU (`_to_device` in `backends/hf.py`): Gemma 4 E4B keeps its 5.25 GiB `embed_tokens_per_layer` there, so the model takes ~10 GiB of VRAM instead of overflowing 16 GB. Ignored on MPS/CPU
- mlx packages are imported inside methods only, so the package imports without them
- `llamacpp` specs name one `gguf_file` in a multi-quant repo (only that file downloads) plus optional `server_args` (e.g. `--n-cpu-moe N` keeps MoE experts in system RAM). The binary is `LLAMA_SERVER_BIN` (setting/env, default `llama-server` on PATH). Server output goes to `RECIPES_TEMP_DIR_PATH/logs/<slug>.log`; `unload` stops the server. Requests are greedy (`temperature=0`) with `enable_thinking=False`
- Scraped data is a durable local cache, never deleted for tests: `prepare_reel` returns `RECIPES_TEMP_DIR_PATH/media/<shortcode>` if complete, else copies an existing `INSTAGRAM_TEMP_DIR_PATH/<shortcode>/{video.mp4,caption.txt}` (from `cli.instagram_html`), and only then scrapes, so each reel hits Instagram at most once
- Benchmark is stage-major: one model in memory at a time; ASR/OCR outputs cache per model under `RECIPES_TEMP_DIR_PATH/cache/{asr,ocr}/<slug>/<shortcode>.json` (delete a folder to re-measure). `pipeline_seconds` follows the production rule (caption time only on a caption hit); stage times for cached ASR/OCR are the originally measured ones
- Run output `RECIPES_TEMP_DIR_PATH/runs/<UTC>/`: `results.jsonl` (all attempts and raw outputs), `summary.csv`, `pipelines.json`, `judge/<shortcode>.md` (evidence + every pipeline's recipe, for manual LLM-judge scoring)

## Work Guidance

- Qwen3-ASR is excluded: it has no Ukrainian
- Tune `GATE_THRESHOLD`, `KEYFRAME_FPS`, `MAX_KEYFRAMES` and `sample_keyframes(diff_threshold=)` from benchmark results, not by guess

## Verification

- `uv run python -m cli.recipe_parser temp/instagram/test.mp4 --pipeline mlx-gemma --force-av`
- `uv run python -m cli.recipe_bench prepare` → `download-models` → `run` (details in `cli/AGENTS.md`)

## Child DOX Index
