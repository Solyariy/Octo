"""Print every registered embedding model with its backend, dim and load kwargs.

Run with:

    uv run python -m cli.embedder_registry
"""

from src.embedders.models import EmbeddersEnum

if __name__ == '__main__':
    for model in EmbeddersEnum:
        print(model.name, model.get_backend(), model.get_dim(), model.get_config())
