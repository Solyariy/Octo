# src/embedders DOX

## Purpose

- Load embedding models, keep them cached on local disk, and expose one encode surface per backend to the rest of the service

## Ownership

- `models.py` — `EmbeddersEnum`, `EmbedderSpec`, and the `EMBEDDING_MODEL_CONFIG` registry (backend, output dim, load kwargs)
- `factory.py` — `get_embedding_manager`, the only supported way to build a manager, plus the `MANAGERS` backend table
- `schemas.py` — `CustomVector`, the id+vector shape for carrying embeddings around
- `managers/base.py` — `BaseEmbeddingManager`, the backend-agnostic lifecycle (`load_model`/`encode_text`/`encode_video`/`unload`/context manager)
- `managers/hf_manager.py` — `GeneralEmbeddingManager`, the sentence-transformers backend
- `managers/cosmos_manager.py` — `CosmosEmbeddingManager`, the `trust_remote_code` `AutoModel` + `AutoProcessor` backend for Cosmos-Embed1

## Local Contracts

- A model is referenced only by an `EmbeddersEnum` member, never by a raw string; adding a model means adding the enum member and its `EMBEDDING_MODEL_CONFIG` entry together. `models.py` raises at import if a member has no entry
- Call sites build managers through `get_embedding_manager(model)`; the concrete class is chosen by `spec.backend`. Do not instantiate a manager class directly
- `spec.dim` is the contract for vector length and is what vector-store collections are sized against: `GeneralEmbeddingManager` passes it as `truncate_dim`, `CosmosEmbeddingManager` emits it natively (768)
- `GeneralEmbeddingManager` is the only path to a `SentenceTransformer`: it checks `MODELS_PATH/<model-id>` on disk first, otherwise downloads with `HF_AUTH_TOKEN` and persists atomically via a sibling `.part` directory. A failed save must leave no partial directory behind and must keep the in-memory model usable
- `CosmosEmbeddingManager` uses the HuggingFace cache layout under `MODELS_PATH` (`cache_dir=`) instead, because `save_pretrained` does not round-trip a remote-code model together with its processor. Both layouts stay inside `MODELS_PATH`
- `load_model()` is idempotent; use the context manager (`with get_embedding_manager(...) as m`) so `unload()` drops references on exit
- `encode_text` is implemented by every backend; `encode_video` raises `NotImplementedError` unless the backend has a video tower. Cosmos text and video vectors share one L2-normalised space, so a dot product is cosine similarity
- `encode_video` accepts file paths or THWC uint8 frame arrays and returns a `(len(videos), dim)` float array; every clip in one call is stacked into a single batch, so callers must chunk large lists themselves
- Model loading and encoding are synchronous and CPU/GPU-blocking; never call them directly inside an async route without offloading
- Video frames are decoded with PyAV (`av`) through `src.utils.video.sample_frames`: `decord` has no macOS wheels and `torchcodec` is deliberately not a dependency because its wheels need FFmpeg dylibs the host lacks — with it installed, even `import sentence_transformers` fails
- Cosmos-Embed1's remote code only loads under transformers 4.x (transformers 5 dropped `find_pruneable_heads_and_indices` and skips the `pos_embed` interpolation hook); `require_supported_transformers()` fails loudly if the pin in `pyproject.toml` is ever relaxed

## Work Guidance

- Log through `LoggerMixin` (`self.log_info` / `log_warning` / `log_error`), inherited from `BaseEmbeddingManager`
- Device and dtype come from `src.utils.models.pick_device` (cuda/bfloat16 → mps/float32 → cpu/float32)
- `QWEN3_4B` and `COSMOS_EMBED1_448P` are the models actually exercised; `COSMOS_EMBED1_448P` is the only one wired into the service. `QWEN3_8B`, `JINA5_OMNI` and `GEMMA_03B` are registered but unproven and their `dim` values are unverified

## Verification

- Smoke scripts live in `cli/`: `uv run python -m cli.qwen`, `uv run python -m cli.nvidia_cosmos`, `uv run python -m cli.embedder_registry` (details in `cli/AGENTS.md`)
