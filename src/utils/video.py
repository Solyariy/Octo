from pathlib import Path

import av
import numpy as np
from PIL import Image


def sample_frames(path: Path | str, num_frames: int) -> np.ndarray:
    """Return `num_frames` evenly spaced RGB frames as a THWC uint8 array.

    Decoding goes through PyAV, which bundles its own FFmpeg: `decord` has no
    macOS wheels and `torchcodec` needs matching system FFmpeg libraries.
    """
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"

        total = stream.frames
        if not total:
            # WebM/Matroska headers usually omit the frame count.
            total = sum(1 for _ in container.decode(stream))
            container.seek(0)
        if total < 1:
            raise RuntimeError(f"No decodable frames in {path}")

        wanted = (
            np.linspace(
                0,
                total - 1,
                num_frames,
            )
            .astype(int)
            .tolist()
        )
        last = max(wanted)
        needed = set(wanted)

        decoded: dict[int, np.ndarray] = {}
        for index, frame in enumerate(container.decode(stream)):
            if index in needed:
                decoded[index] = frame.to_ndarray(format="rgb24")
            if index >= last:
                break

    missing = [i for i in wanted if i not in decoded]
    if missing:
        raise RuntimeError(f"Could not decode frame indices {missing} from {path}")

    return np.stack([decoded[i] for i in wanted])


def sample_keyframes(
    path: Path | str,
    fps: float = 1.0,
    max_frames: int = 60,
    diff_threshold: float = 6.0,
) -> list[Image.Image]:
    """Sample frames at `fps` and drop near-duplicates of the last kept frame.

    Similarity is the mean absolute difference of 64x64 grayscale thumbnails (0-255 scale),
    so a static text overlay is kept once. At most `max_frames` frames are returned, spread
    evenly over the clip when there are more candidates.
    """
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        time_base = float(stream.time_base) if stream.time_base else None

        candidates: list[Image.Image] = []
        next_ts = 0.0
        for index, frame in enumerate(container.decode(stream)):
            if frame.pts is not None and time_base:
                ts = frame.pts * time_base
            else:
                ts = index / float(stream.average_rate or 30)
            if ts + 1e-6 < next_ts:
                continue
            next_ts = ts + 1.0 / fps
            candidates.append(frame.to_image())

    if not candidates:
        raise RuntimeError(f"No decodable frames in {path}")

    kept: list[Image.Image] = []
    last_thumb: np.ndarray | None = None
    for image in candidates:
        thumb = np.asarray(
            image.convert("L").resize((64, 64)),
            dtype=np.float32,
        )
        if last_thumb is not None and np.abs(thumb - last_thumb).mean() < diff_threshold:
            continue
        kept.append(image)
        last_thumb = thumb

    if len(kept) > max_frames:
        picks = (
            np.linspace(
                0,
                len(kept) - 1,
                max_frames,
            )
            .astype(int)
            .tolist()
        )
        kept = [kept[i] for i in picks]
    return kept


def video_duration(path: Path | str) -> float:
    """Length of the first video stream in seconds, from the container header when present."""
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        if stream.duration is not None and stream.time_base is not None:
            return float(stream.duration * stream.time_base)
        if container.duration is not None:
            return container.duration / av.time_base
        if stream.frames and stream.average_rate:
            return float(stream.frames / stream.average_rate)
    raise RuntimeError(f"Cannot determine the duration of {path}")
