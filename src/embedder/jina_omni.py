"""Jina Omni Embeddings — multi-modal encoder (text, image, video, audio).

Video frame sampling:
  By default, videos are sampled at 1 frame per second (FPS=1). You can
  change this globally or per-call:

      import src.embedder.jina_omni as jina
      jina.set_video_fps(0.5)          # 0.5 fps — global
      jina.set_video_fps(None)         # reset to fixed 32 frames uniformly
      emb = jina.embed_video("clip.mp4", video_fps=2.0)  # per-call override

  The underlying custom_st.py module reads the video's native FPS via pyav,
  then targets `round(duration_secs × video_fps)` frames, capped at 32.
"""
import os.path
import sys

import torch

from sentence_transformers import SentenceTransformer

MODELS_PATH = "/Users/oleksandrskromnov/PycharmProjects/Octo/models"
JINA_PATH = MODELS_PATH + "/jina"
_MODEL = None
_VIDEO_FPS: float | None = 1.0  # default: 1 frame per second of video


def _set_module_attr(fps: float | None) -> None:
    """Push the current FPS value into the underlying custom_st module."""
    import sys as _sys
    mod = _sys.modules.get(type(_MODEL[0]).__module__) if _MODEL else None
    if mod is not None and hasattr(mod, "VIDEO_TARGET_FPS"):
        mod.VIDEO_TARGET_FPS = fps


def get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        if os.path.exists(JINA_PATH):
            _MODEL = SentenceTransformer(JINA_PATH)
        else:
            _MODEL = SentenceTransformer(
                "jinaai/jina-embeddings-v5-omni-small",
                trust_remote_code=True,
                model_kwargs={"default_task": "retrieval"},
            )
            # _MODEL.save(JINA_PATH)
        _set_module_attr(_VIDEO_FPS)
    return _MODEL


def set_video_fps(fps: float | None) -> None:
    """Set video frame sampling rate.

    Args:
        fps: Target frames per second of source video.
             ``None`` falls back to the original fixed 32-frame uniform sampling.
    """
    global _VIDEO_FPS
    _VIDEO_FPS = fps
    if _MODEL is not None:
        _set_module_attr(fps)


def get_video_fps() -> float | None:
    """Return the current video frame sampling rate."""
    return _VIDEO_FPS


# ── Public encoding helpers ──────────────────────────────────────────

def embed_text(text: str) -> list[float]:
    return get_model().encode(text).tolist()


def embed_query(text: str) -> list[float]:
    return get_model().encode_query(text).tolist()


def embed_document(text_or_url: str) -> list[float]:
    return get_model().encode_document(text_or_url).tolist()


def embed_image(url_or_path: str) -> list[float]:
    return get_model().encode(url_or_path).tolist()


def embed_video(url_or_path: str, *, video_fps: float | None = None) -> list[float]:
    """Encode a video file (path or URL).

    Args:
        url_or_path: Local path or URL to a video.
        video_fps:   Per-call override for frames-per-second sampling.
                      If omitted, the module-level default is used.
    """
    if video_fps is not None:
        old = _VIDEO_FPS
        set_video_fps(video_fps)
        try:
            return get_model().encode(url_or_path).tolist()
        finally:
            set_video_fps(old)
    return get_model().encode(url_or_path).tolist()


def embed_fused(items: tuple[str, ...]) -> list[float]:
    return get_model().encode(items).tolist()


if __name__ == "__main__":
    # ── quick smoke test ──────────────────────────────────────────────
    v_vec = embed_video("https://storage.googleapis.com/walkfit/Assets%20Folder/DONE/task_43b84b1d_7e22a072/1f2bd802-2112-4cd0-8ae2-81953f627e5b.mp4")
    print(f"Video embedding — dim={len(v_vec):>4}  first 5 values: {v_vec[:5]}")
