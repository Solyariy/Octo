"""Manual smoke test for NVIDIA Cosmos-Embed1 video/text embeddings.

Run with:

    uv run python -m src.embedders.tests.nvidia_cosmos

Ranks six captions against a sample clip through `CosmosEmbeddingManager`, so it
also exercises the shared video/text space: both sides come back as 768-d
normalised vectors that can be compared directly.
"""

import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np

from src.embedders.factory import get_embedding_manager
from src.embedders.models import EmbeddersEnum


VIDEO_URL = "https://upload.wikimedia.org/wikipedia/commons/3/3d/Branko_Paukovic%2C_javelin_throw.webm"

CAPTIONS = [
    "a person riding a motorcycle in the night",
    "a car overtaking a white truck",
    "a video of a knight fighting with a sword",
    "a man wearing red spandex throwing a javelin",  # expected match
    "a young man javelin throwing during the evening",  # distractor
    "a man throwing a javelin with both hands",  # distractor
]
EXPECTED_CAPTION_INDEX = 3


def download_video(url: str, destination: Path) -> Path:
    if destination.exists() and destination.stat().st_size > 0:
        print(f"Using cached video: {destination}")
        return destination

    print(f"Downloading {url}")
    # Wikimedia rejects the default urllib user agent.
    request = urllib.request.Request(url, headers={"User-Agent": "octo-smoke-test/0.1"})
    with urllib.request.urlopen(request) as response, destination.open("wb") as file:
        while chunk := response.read(1 << 20):
            file.write(chunk)
    return destination


def main() -> int:
    video_path = download_video(VIDEO_URL, Path(tempfile.gettempdir()) / "javelin_throw.webm")

    with get_embedding_manager(EmbeddersEnum.COSMOS_EMBED1_448P) as manager:
        video_embeddings = manager.encode_video([video_path])
        text_embeddings = manager.encode_text(CAPTIONS)

        print(f"\nVideo embeddings: {video_embeddings.shape}")
        print(f"Text embeddings:  {text_embeddings.shape}")

        if video_embeddings.shape[1] != manager.output_dim:
            print(
                f"\nFAIL: expected {manager.output_dim}-d vectors, got {video_embeddings.shape[1]}",
                file=sys.stderr,
            )
            return 1

        # Both sides are L2-normalised, so the dot product is cosine similarity.
        similarities = (video_embeddings @ text_embeddings.T)[0]

        print("\nCaption similarities:")
        for index in np.argsort(-similarities):
            print(f"  {similarities[index]:.4f}  {CAPTIONS[index]}")

        best = int(np.argmax(similarities))
        print(f"\nBest match: {CAPTIONS[best]}")

        if best != EXPECTED_CAPTION_INDEX:
            print(
                f"\nWARNING: expected '{CAPTIONS[EXPECTED_CAPTION_INDEX]}' to rank first.",
                file=sys.stderr,
            )
            return 1

        print("OK: the expected caption ranks first.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
