# src/utils DOX

## Purpose

- Dependency-light helpers shared across the service: logging, type aliases, time/id generation, file and text utilities

## Ownership

- `logs.py` — structlog configuration, `main_logger`, `Logger` static facade, `LoggerMixin`
- `order.py` — `get_model_path`, UTC/Kyiv clocks, `get_uuid_str`, `get_log_id`
- `annotations.py` — `StrUUID`, `LocalFilePath`, `Timestamp` pydantic-annotated `NewType`s
- `models.py` — `pick_device`, the torch device/dtype choice shared by every model backend
- `video.py` — `sample_frames`, PyAV frame sampling for video models

## Local Contracts

- Modules here must not import from `src.db` or `src.embedders`; only `src.settings`, `src.utils.*`, and third-party packages
- structlog is configured once, at import of `logs.py`, rendering to stdout with `ConsoleRenderer` at DEBUG level and uvicorn loggers pinned to WARNING; do not reconfigure it elsewhere
- Classes log via `LoggerMixin`, which prefixes `[ClassName]` and passes `increase_depth=2`; free functions call `Logger.info/debug/warning/error` directly
- `Logger` methods are wrapped by `inject_traceback`, which walks the caller frame to attach `(file, line)` — any new log level must keep the `increase_depth` contract or locations will point at the wrong frame
- `Logger.error` always attaches `traceback.format_exc()`, so call it from inside an `except` block
- Every log line carries `log_id` from `get_log_id()`, which lazily fills the `LOG_ID` ContextVar defined in `src.settings`; set it per request to correlate a trace
- `models.py` and `video.py` may import torch and PyAV, but must stay model-agnostic: no HuggingFace model ids, no manager classes

## Work Guidance

- Keep helpers pure and synchronous; anything needing a datastore or a model belongs in its own package
- `Logger.warning` accepts `error=` but drops it; pass details as keyword fields instead

## Verification

- No automated checks
