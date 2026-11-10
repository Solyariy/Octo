import argparse
import asyncio
from pathlib import Path

from sqlalchemy.exc import NoResultFound

from src.api.schemas import InputPost
from src.db.postgres.init_db import postgres_lifespan
from src.db.postgres.manager import PostgresManager

DEFAULT_FILE = Path(__file__).with_name("seed_urls.txt")


def read_urls(path: Path) -> list[str]:
    lines = (line.strip() for line in path.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


async def seed(path: Path, email: str) -> int:
    posts = [InputPost(url=url) for url in read_urls(path)]
    if not posts:
        print(f"no urls in {path}")
        return 1
    async with postgres_lifespan() as (_, session_factory):
        pg_manager = PostgresManager(session_factory)
        try:
            user = await pg_manager.get_user_by_email(email)
        except NoResultFound:
            print(f"user {email!r} not found; run `make admin` first")
            return 1
        inserted = await pg_manager.insert_posts_bulk(posts, user)
    print(
            f"seeded {len(inserted)} of {len(posts)} posts as PENDING for {email} "
            f"({len(posts) - len(inserted)} already existed)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Insert seed post urls as PENDING posts")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--email", default="admin@octo.local", help="owner of the seeded posts")
    args = parser.parse_args()
    return asyncio.run(seed(args.file, args.email))


if __name__ == "__main__":
    raise SystemExit(main())
