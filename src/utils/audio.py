from pathlib import Path

import av
import numpy as np

SPEECH_SAMPLE_RATE = 16000


def load_audio(path: Path | str, sample_rate: int = SPEECH_SAMPLE_RATE) -> np.ndarray:
    """Decode the first audio stream to mono float32 in [-1, 1] at `sample_rate`.

    Goes through PyAV, never torchcodec. A file without an audio stream yields an empty array.
    """
    with av.open(str(path)) as container:
        if not container.streams.audio:
            return np.zeros(0, dtype=np.float32)
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(
            format="flt",
            layout="mono",
            rate=sample_rate,
        )
        chunks: list[np.ndarray] = []
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                chunks.append(resampled.to_ndarray().reshape(-1))
        for resampled in resampler.resample(None):
            chunks.append(resampled.to_ndarray().reshape(-1))

    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32, copy=False)
