"""Manual smoke test for EmbeddingGemma 2 text/image/video embeddings.

Run with:

    uv run python -m cli.embeddinggemma

Embeds a sample clip, a sample photo and four captions in one
`OmniEmbeddingManager.encode_inputs` call, then checks every vector is `output_dim`-wide
and that each medium ranks its own caption first in the shared space.
"""

import sys
import tempfile
from pathlib import Path

import numpy as np

from cli.nvidia_cosmos import VIDEO_URL, download_video
from src.embedders.factory import get_embedding_manager
from src.embedders.models import EmbeddersEnum
from src.enums import Modality

IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg"

CAPTIONS = [
    "a man wearing red spandex throwing a javelin",  # expected for the video
    "a close-up photo of a cat",  # expected for the image
    "a car overtaking a white truck",
    "a person riding a motorcycle in the night",
]
EXPECTED = {"video": 0, "image": 1}


def main() -> int:
    temp = Path(tempfile.gettempdir())
    video_path = download_video(VIDEO_URL, temp / "javelin_throw.webm")
    image_path = download_video(IMAGE_URL, temp / "cat03.jpg")

    inputs = [(Modality.VIDEO, video_path), (Modality.IMAGE, image_path)]
    inputs += [(Modality.TEXT, caption) for caption in CAPTIONS]

    with get_embedding_manager(EmbeddersEnum.GEMMA2_OMNI) as manager:
        vectors = manager.encode_inputs(inputs)
        print(f"\nEmbeddings: {vectors.shape}")
        if vectors.shape != (len(inputs), manager.output_dim):
            print(
                f"\nFAIL: expected {(len(inputs), manager.output_dim)}, got {vectors.shape}",
                file=sys.stderr,
            )
            return 1

    norms = np.linalg.norm(vectors, axis=1)
    print(f"Norms: {np.round(norms, 4).tolist()}")

    failed = False
    text_vectors = vectors[2:]
    for row, name in enumerate(("video", "image")):
        # Vectors are L2-normalised, so the dot product is cosine similarity.
        similarities = text_vectors @ vectors[row]
        print(f"\n{name} caption similarities:")
        for index in np.argsort(-similarities):
            print(f"  {similarities[index]:.4f}  {CAPTIONS[index]}")
        if int(np.argmax(similarities)) != EXPECTED[name]:
            print(f"FAIL: expected '{CAPTIONS[EXPECTED[name]]}' first", file=sys.stderr)
            failed = True

    if failed:
        return 1
    print("\nOK: every medium ranks its own caption first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
