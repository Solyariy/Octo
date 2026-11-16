# Recipe parser: model benchmark results (CUDA): Handoff

*Date: 2026-11-17 · Purpose: what was learned from benchmarking recipe-extraction models on the RTX 4060 Ti PC, and what to do next · Companion to `docs/recipe-parser-handoff.md` (module and build history) and `docs/pc-ssh-gpu-handoff.md` (how to drive the PC: SSH, rsync, llama-server)*

## 1. Where things stand

| Area | State |
|---|---|
| Benchmark runs on the Ubuntu PC over `ssh pc` (RTX 4060 Ti 16 GB) | Working. Code is pushed with rsync, not git (see the companion PC doc) |
| hf-* pipelines on CUDA (bf16 transformers) | Working. Gemma 4 E4B needs `cpu_modules` to fit (section 3) |
| New `llamacpp` backend (GGUF via `llama-server`) | Working. 5 GGUF SLMs ran on 4 reels with 0 final failures |
| Valid runs | `runs/20261116T210634Z` (hf-qwen, hf-gemma after the JSON fix) and `runs/20261116T220913Z` (7 pipelines, same ASR+OCR, only the SLM differs). Both are copied to the Mac under `temp/recipes/runs/` |
| Invalid run | `runs/20261116T202411Z`: 7 of 8 recipes empty because of a validation bug (section 5). Ignore it |
| MLX pipelines (`mlx-qwen9b`, `mlx-gemma`) | Not re-run; they run on the Mac only |
| Code | All changes are **uncommitted** on the Mac (`main`). The PC holds an rsync copy |

## 2. Test set (4 reels, `cli/seed_urls_recipies.txt`)

| Shortcode | Content | Recipe lives in | Role |
|---|---|---|---|
| `Ddot2x-IGIO` | Hot chocolate. Ukrainian description has a full recipe (7 ingredients, 4 steps, an optional starch tip at the end) | Description | Tests the description-only path (`path="caption"`) |
| `DcqUwgqugH2` | "Any legume into tofu". English, the description is an ebook ad | Speech | Generic recipe ("any legume") |
| `DflKar5OotU` | Restaurant garlic-knot sliders. English, description is hashtags only | Speech | Long step sequence |
| `Dfkc1b-ofqG` | Ukrainian "what I cooked this week", **5 dishes** | Speech + on-screen list | **Deliberate stress test (user): kept to break models and watch their behaviour. Empty or odd output here is acceptable and is the signal being monitored** |

The smoke clip `temp/recipes/media/test/` (music only, no caption) is not in the test set and is never benchmarked.

## 3. Decisions

- **Same ASR+OCR for every SLM comparison.** The 7-pipeline run uses `hf-whisper-large-v3-turbo` + `hf-qwen3.5-2b-ocr` (cached) for all pipelines, so only the SLM differs. The earlier hf-qwen vs hf-gemma comparison mixed OCR and SLM and could not be read cleanly.
- **Quantised bigger models beat bf16 small ones** (the user's hypothesis, confirmed on these 4 reels).
- **Use llama.cpp GGUF, not bitsandbytes.** Official Google QAT q4_0 GGUFs exist, Unsloth publishes many Qwen3.5 quants, and MoE experts can spill into system RAM (`--n-cpu-moe`). `llama-server` was already built with CUDA on the PC. Qwen's official GPTQ-Int4 checkpoints are too large (27B = 28 GB, 35B-A3B = 23 GB), so they were rejected.
- **Strict schema, no JSON repair.** `StrictModel` (`extra="forbid"`) makes wrappers and schema echoes count as validation errors that go through the retry prompt. The parser deliberately does not unwrap `{"Recipe": ...}`, because JSON failures are a benchmark metric.
- **Prompt shows a type template (`RECIPE_SHAPE`), not the Pydantic JSON Schema.** After this change, every model produced valid JSON on the first attempt (one exception, section 5).
- **Gemma 4 E4B bf16 on CUDA:** its 5.25 GiB `embed_tokens_per_layer` stays on CPU (`ParserModelSpec.cpu_modules`, applied only on CUDA). Without it the 15 GB model runs out of memory at prefill; with it, 9.6 GiB loaded and 10.7 GiB peak.
- **Rejected:** Gemma 4 31B dense (a Q3 quant is 13.7 GB or more, too tight), Qwen3.5-27B Q4 (14.6–15.6 GB, no room for the KV cache).

## 4. Model results (`runs/20261116T220913Z`, 4 reels, CUDA)

### Models tested

| Slug | Model / quant | Size | Fit on 16 GB |
|---|---|---|---|
| `hf-qwen3.5-4b` | Qwen3.5-4B bf16 (transformers) | ~9 GB | GPU |
| `hf-gemma-4-e4b` | Gemma 4 E4B-it bf16 (transformers) | 15 GB | GPU with per-layer embeddings on CPU |
| `gguf-qwen3.5-9b-q8` | unsloth `Qwen3.5-9B-Q8_0.gguf` | 8.9 GB | GPU |
| `gguf-gemma-4-12b-qat-q4` | google `gemma-4-12b-it-qat-q4_0.gguf` | 6.5 GB | GPU |
| `gguf-gemma-4-26b-a4b-qat-q4` | google `gemma-4-26B_q4_0-it.gguf` (MoE, 4B active) | 13.45 GB | GPU, tight |
| `gguf-qwen3.5-27b-q3kxl` | unsloth `Qwen3.5-27B-UD-Q3_K_XL.gguf` (dense) | 13.45 GB | GPU, tight |
| `gguf-qwen3.5-35b-a3b-q4kxl` | unsloth `Qwen3.5-35B-A3B-UD-Q4_K_XL.gguf` (MoE, 3B active) | 20.7 GB | `--n-cpu-moe 16`, 14.3 GB peak VRAM |

### Speed (measured)

| Pipeline | Load s | Combine SLM call, mean s | Reel mean s | Decode tok/s (smoke test) | JSON errors |
|---|---|---|---|---|---|
| gguf-gemma26b | 15.2 | **7.4** | **25.5** | 79 | 1 parse (retry fixed it) |
| gguf-qwen35b | 21.2 | 11.7 | 28.7 | 56 | 0 |
| gguf-gemma12b | 7.3 | 17.2 | 34.3 | 34 | 0 |
| hf-qwen-q2ocr (Qwen3.5-4B) | 10.5 | 20.6 | 38.9 | — | 0 |
| hf-gemma (Gemma E4B) | 13.7 | 26.3 | 44.1 | — | 0 |
| gguf-qwen9b | 13.2 | 34.1 | 51.4 | — | 0 |
| gguf-qwen27b | 16.7 | 41.4 | 61.1 | 17 | 0 |

Shared stages: ASR 1.3 s per reel. OCR `hf-qwen3.5-2b-ocr` 28 s per reel. OCR `hf-paddleocr-vl-1.5` 238 s per reel on CUDA (~12 min per reel on M5 MPS).

### Quality per reel (manual review)

| SLM | Hot chocolate (description) | Tofu | Sliders | 5-dish stress reel |
|---|---|---|---|---|
| **Qwen3.5-27B Q3** | ✅ Includes the optional starch tip ("cornstarch": the source says only "starch") | ✅ | ✅ servings=6 inferred, not stated | ✅ **Only correct one**: all 5 dishes, ingredients tagged per dish, correct translations (puff pastry, cream cheese, herring, flatbread) |
| **Gemma 26B-A4B QAT** | ✅ Starch tip; drops the 80 °C from the step text and "pinch" for pepper/salt | ✅ | ✅ Most compact (5 merged steps) | Empty; the first attempt was prose ("no single recipe"), a parse error |
| Qwen3.5-35B-A3B Q4 | ✅ Misses the starch tip | ✅ | ✅ | Empty |
| Gemma 12B QAT | ✅ Starch tip | ✅ | ✅ | Empty |
| Qwen3.5-9B Q8 | ✅ | ⚠️ **Invents "10 oz legumes, 40 oz water"** from the numbers on a measuring jug | ⚠️ servings=6 | ⚠️ All dishes, but "ricotta" (wrong) and "dill" (not in the sources) |
| Qwen3.5-4B bf16 | ✅ | ❌ No ingredients at all | ✅ 14 clean steps | ❌ **"Ossetra caviar", "fish fillet"** (from OCR noise) |
| Gemma E4B bf16 | ⚠️ "pepper **gives color**" (mistranslation; the source means it sets off the flavour) | ✅ | ⚠️ Copies speech word for word ("his thick vodka sauce", "until it looks like this") | ❌ First dish only, "phyllo" (should be puff pastry), meat reduced to "filling" |

### Stand-out points

- **Bigger SLMs absorb OCR noise.** Qwen3.5-2B OCR read the Ukrainian "оселедцем" (herring) as the Russian "осетровцем" (sturgeon). The 4B SLM turned that into "ossetra caviar"; the 27B followed the transcript and wrote "herring".
- **Only the bigger models capture trailing details**, such as the optional starch tip at the end of the hot chocolate description.
- **On the 5-dish stress reel the families split:** the Gemma models and Qwen 35B-A3B return an empty recipe; the dense Qwen models (9B, 27B) produce a combined menu. This is expected and acceptable, because the reel exists to observe this behaviour.
- **Invented values come from OCR numbers and from inference:** jug-scale numbers became quantities (9B), and "6 knots" became servings=6 (9B, 27B). No model invented temperatures or times.
- **Nobody invents quantities from the description or the speech.** Unstated quantities stay null.
- **Speed is driven by active parameters:** the MoE models (26B-A4B, 35B-A3B) are the fastest despite their size. The dense 27B Q3 is bandwidth-bound at 17 tok/s.

### OCR comparison (Qwen3.5-2B vs PaddleOCR-VL 1.5)

| | PaddleOCR-VL 1.5 | Qwen3.5-2B |
|---|---|---|
| Readability | Broken Cyrillic ("чӀэбурреп"), CJK characters, runs of `O O O…` and `1000…` | Mostly clean |
| Fabrication | Small fragments ("ed ginger 125 10 cm x") and the sentence "The image is too blurry…" | **Invented a whole Russian marinade recipe** on one notebook frame |
| Language | Keeps Ukrainian, broken | **Turns Ukrainian into Russian** ("Вафельный", "горячий", "с осетровцем") |
| Junk | — | Chat-template leaks (`user`, `assistant<think>`) and fillers (`none`, `N/A`, `no text`) |
| Speed | 238 s per reel | 28 s per reel |

Paddle's errors are visible garbage. Qwen-2B's errors are plausible and in Russian, and they reached a small SLM's recipe. Preferred choice: Qwen3.5-2B for speed and readability, plus the clean-up listed in section 6.

## 5. Gotchas

- **Silent empty recipes (fixed).** `Recipe` used to accept unknown keys and every field is optional, so `{"Recipe": {...}}` (Gemma) and an echoed JSON Schema (`{"$defs": ...}`, Qwen) validated as empty recipes with "0 JSON errors". Both causes are fixed: `StrictModel` plus the `RECIPE_SHAPE` prompt. `prompts.py` fails at import if the `RECIPE_SHAPE` keys drift from the `Recipe` fields.
- **An empty-but-valid recipe looks incomplete**, so a reel whose description holds a full recipe still falls through to the audio/video path. When `path` looks wrong, check the raw output first.
- **Gemma 26B-A4B can answer in prose** ("…required to form a single recipe.") instead of JSON. The retry handles it.
- **Qwen3.5 on transformers lacks fast kernels** (`flash-linear-attention`, `causal_conv1d`), so hf-qwen timings are pessimistic. Installing them on Linux would speed it up.
- **`results.jsonl` is compact JSONL as written.** A 929-line copy seen on the Mac had been reformatted after the copy, probably by the IDE. Parse the PC original if in doubt.

## 6. Recommendations and caveats

**Recommend:**
- **Quality pick: Qwen3.5-27B UD-Q3_K_XL** (about 61 s per reel end to end, fine for background processing).
- **Speed pick: Gemma 4 26B-A4B QAT q4_0** (about 25 s per reel), nearly the same quality on single-recipe reels.
- **Drop** Qwen3.5-9B Q8 (invents quantities from OCR) and the bf16 small models (Qwen3.5-4B, Gemma E4B).
- **OCR:** Qwen3.5-2B, with clean-up.

**Caveats:**
- Only 4 reels, and quality was reviewed by hand. This is a strong signal, not proof. There is no LLM-judge score yet.
- Only one Ukrainian-speech reel, and it is the 5-dish stress reel. Translation quality on Ukrainian speech is barely tested.
- One quant per model was tested. A higher quant of the 27B (IQ4_XS, 13.95 GB) might be better but has little VRAM headroom.
- All runs used greedy decoding (`temperature=0`) with `enable_thinking=False`. Thinking mode was not tested.

## 7. Next steps

- [ ] Commit the uncommitted work on the Mac when the user asks: StrictModel and RECIPE_SHAPE, the cpu_modules offload, the llamacpp backend, new pipelines/specs/settings, docs. Then re-sync the PC
- [ ] Score `temp/recipes/runs/20261116T220913Z/judge/*.md` with an LLM judge (user)
- [ ] Add more reels, especially Ukrainian speech and on-screen-only recipes; keep `Dfkc1b-ofqG` as the stress reel
- [ ] OCR clean-up for Qwen3.5-2B: strip template leaks and fillers (`none`, `N/A`, `no text`, `user`, `assistant<think>`), add a "keep the source language, do not translate" hint, and drop duplicate lines across frames
- [ ] Optional: try Qwen3.5-27B IQ4_XS, and lower `--n-cpu-moe` for the 35B-A3B (14.3 GB peak leaves room)
- [ ] Optional: install `flash-linear-attention` and `causal_conv1d` on the PC for fair hf-qwen timings
- [ ] Re-run the MLX pipelines on the Mac with the fixed prompt
- [ ] Tune the gate threshold and keyframe parameters from results; later wire the chosen pipeline into the API / `OmniPipeline`

*Sources: benchmark outputs in `temp/recipes/runs/20261116T210634Z` and `20261116T220913Z` (summary.csv, results.jsonl, judge/*.md); llama-server timing lines and nvidia-smi on the PC; HF API file listings for model sizes; user statements (the 5-dish reel is an intentional stress test; English/Ukrainian only). Quality verdicts are manual review by the assistant, not measured scores.*
