from pathlib import Path

import av
import numpy as np


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

        wanted = np.linspace(0, total - 1, num_frames).astype(int).tolist()
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
