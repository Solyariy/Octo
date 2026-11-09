import argparse
import asyncio

from qdrant_client import models

from src.db.postgres.init_db import postgres_lifespan
from src.db.postgres.manager import PostgresManager
from src.db.qdrant.init_db import init_qdrant_collections, qdrant_client_lifespan
from src.db.qdrant.models import get_collection
from src.enums import ProcessingStatus
from src.services.omni_pipeline import OmniPipeline


async def backfill(*, dry_run: bool) -> int:
    """Copy `posts.created_at` into the payload of every point of each `SUCCESS` post."""
    collection = get_collection(OmniPipeline.EMBEDDER).collection_name
    async with postgres_lifespan() as (_, session_factory), qdrant_client_lifespan() as client:
        await init_qdrant_collections(client)  # makes sure the created_at index exists
        posts = await PostgresManager(session_factory).get_posts_by_status(ProcessingStatus.SUCCESS)
        print(f"{len(posts)} success posts; collection={collection}; dry_run={dry_run}")
        for post in posts:
            created_at = post.created_at.isoformat()
            if not dry_run:
                await client.set_payload(
                        collection_name=collection,
                        payload={"created_at": created_at},
                        points=models.Filter(
                                must=[
                                        models.FieldCondition(
                                                key="post_id",
                                                match=models.MatchValue(value=str(post.id)),
                                        )
                                ]
                        ),
                )
            print(f"{post.id} created_at={created_at}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
            description="Back-fill created_at into Qdrant payloads of already-processed posts"
    )
    parser.add_argument("--dry-run", action="store_true", help="list posts, write nothing")
    args = parser.parse_args()
    return asyncio.run(backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
