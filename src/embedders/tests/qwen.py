"""Manual smoke test for the Qwen3 embedding model via GeneralEmbeddingManager.

Run with:

    uv run python -m src.embedders.tests.qwen
"""

import sys
import time

from src.embedders.factory import get_embedding_manager
from src.embedders.models import EmbeddersEnum


SAMPLE_TEXTS = [
    # ~500 tokens: paraphrase of the fox sentence, expanded into a long passage.
    "The quick brown fox jumps over the lazy dog, darting across the dewy meadow at dawn while the slumbering "
    "canine barely stirs from its rest beneath the old oak tree. This familiar scene, often reduced to a single "
    "sentence used to display every letter of the alphabet, unfolds here into something far richer when given the "
    "space to breathe. The fox, a creature of remarkable agility and cunning, has long captured the human "
    "imagination across cultures and centuries, appearing in folklore from Aesop's fables to the trickster tales "
    "of Native American tradition, where it is invariably portrayed as clever, elusive, and resourceful. Its "
    "russet coat gleams in the pale morning light as it vaults over the motionless hound, muscles coiling and "
    "releasing in a single fluid motion honed by countless generations of evolutionary pressure. The dog, by "
    "contrast, represents domesticity and loyal torpor, a companion species shaped by ten thousand years of "
    "cohabitation with humans into an animal that prizes comfort and routine above the desperate ingenuity "
    "required of its wild cousin. Together they form a tableau of contrast: wild versus tame, swift versus slow, "
    "alert versus drowsy, a miniature drama that plays out in backyards and woodlots the world over whenever "
    "these two lineages happen to cross paths. Observers of such moments often remark on the strange symmetry "
    "of it, the way the fox's bound seems almost choreographed, as though the animal were performing for an "
    "unseen audience, while the dog's indifference suggests either profound trust or simple exhaustion after a "
    "long night of guarding a flock it has never truly had to defend. Either way, the encounter is fleeting; "
    "the fox vanishes into the hedgerow within seconds, its brush disappearing last, and the dog eventually "
    "lifts its head, sniffs the air as if dimly aware that something has passed, then settles back down to "
    "resume the nap that was so briefly, so inconsequentially interrupted.",
    # ~500 tokens: same meaning, reworded heavily (paraphrase pair).
    "A swift dark-furred fox bounds over a drowsy hound, racing across the mist-covered field at first light "
    "while the lethargic dog scarcely rouses from its slumber beneath an ancient oak. This iconic image, "
    "typically compressed into one pangrammatic phrase designed to showcase each letter of the English "
    "alphabet, expands here into a considerably more detailed portrait when afforded the room to develop. The "
    "fox, an animal of extraordinary nimbleness and guile, has consistently seized human interest throughout "
    "cultures and eras, surfacing in mythology ranging from the fables of ancient Greece to the coyote-and-fox "
    "narratives of indigenous North American peoples, in each case depicted as sly, slippery, and adaptable. "
    "Its copper pelt shimmers in the weak dawn glow as it leaps clear of the stationary dog, sinews tensing "
    "and unfurling in one continuous movement refined through innumerable generations of natural selection. "
    "The dog, on the other hand, embodies domestication and faithful sluggishness, a partner species molded "
    "by millennia of shared living with people into a creature that values warmth and predictability above the "
    "frantic inventiveness demanded of its feral relative. Paired, they constitute a picture of opposition: "
    "feral against domestic, rapid against sluggish, vigilant against drowsy, a small theatre enacted in "
    "gardens and scrubland everywhere these two bloodlines happen to intersect. Witnesses to such instants "
    "frequently note the peculiar balance of the thing, the manner in which the fox's leap appears almost "
    "staged, as if the beast were entertaining an invisible spectator, whereas the dog's apathy implies either "
    "deep confidence or mere fatigue following a lengthy vigil over a flock it has never genuinely needed to "
    "protect. Regardless, the meeting is momentary; the fox melts into the thicket within moments, its tail "
    "the last thing visible, and the dog at last raises its muzzle, sniffs the breeze as though faintly "
    "conscious that a presence has swept by, then lowers itself once more to continue the doze so briefly, so "
    "trivially disturbed.",
    # ~500 tokens: unrelated topic (quantum entanglement), expanded.
    "Quantum entanglement is a phenomenon in which two or more particles become linked so that the quantum "
    "state of each cannot be described independently of the others, even when separated by vast distances, a "
    "connection that Albert Einstein famously derided as spooky action at a distance yet which has been "
    "repeatedly and rigorously confirmed by experiment over the past several decades. When two particles are "
    "entangled, a measurement performed on one instantly determines the corresponding property of the other, "
    "irrespective of the spatial gap between them, a result that initially appears to violate the principle "
    "that information cannot travel faster than the speed of light. Physicists have resolved this tension by "
    "emphasizing that entanglement cannot be used to transmit usable information, since the outcome of each "
    "individual measurement is fundamentally random and only the correlation between paired results reveals "
    "the underlying link. The mathematical framework describing this behavior emerged from the work of John "
    "Stewart Bell, whose eponymous inequality theorem provided a testable boundary between the predictions of "
    "classical local hidden-variable theories and those of genuine quantum mechanics; experiments performed by "
    "Alain Aspect and others in the 1980s, and more recently with cosmological distances, have consistently "
    "found violations of Bell's inequality, confirming that nature is irreducibly nonlocal in this restricted "
    "sense. Beyond its foundational importance, entanglement now underpins emerging technologies including "
    "quantum cryptography, where the no-cloning theorem guarantees that any eavesdropping attempt disturbs the "
    "shared key and is thus detectable, quantum teleportation, in which an unknown quantum state is "
    "transferred between distant stations using a shared entangled pair and classical communication, and "
    "quantum computation, where entangled qubits allow certain algorithms to achieve speedups unattainable on "
    "classical hardware. Researchers continue to push the boundaries of how many particles can be entangled, "
    "over what distances, and for how long, with each advance sharpening our understanding of a universe that "
    "refuses, at its smallest scales, to conform to the intuitions forged in the macroscopic world of everyday "
    "experience.",
]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def main() -> int:
    start = time.perf_counter()
    manager = get_embedding_manager(EmbeddersEnum.QWEN3_4B)

    with manager:
        manager.log_info("Encoding sample texts", count=len(SAMPLE_TEXTS))
        embeddings = manager.encode_text(SAMPLE_TEXTS)

        dim = len(embeddings[0])
        print(f"\nEmbedding dimension: {dim}")
        print(f"Number of texts:     {len(embeddings)}\n")

        for i, (text, emb) in enumerate(zip(SAMPLE_TEXTS, embeddings)):
            preview = text if len(text) <= 60 else text[:57] + "..."
            print(f"[{i}] {preview}")
            print(f"    first 5 dims: {emb[:5]}")
            print(f"    norm:         {sum(x * x for x in emb) ** 0.5:.6f}")

        print("\nCosine similarities:")
        sim_01 = cosine_similarity(embeddings[0], embeddings[1])
        sim_02 = cosine_similarity(embeddings[0], embeddings[2])
        print(f"  text[0] vs text[1] (paraphrase): {sim_01:.4f}")
        print(f"  text[0] vs text[2] (unrelated):  {sim_02:.4f}")

        spent = time.perf_counter() - start
        print("TIME:", spent)

        if sim_01 <= sim_02:
            print("\nWARNING: paraphrase similarity not higher than unrelated — "
                  "model may need a prompt prefix or normalization.",
                  file=sys.stderr)
            return 1

        print("\nOK: paraphrase pair is more similar than the unrelated pair.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
