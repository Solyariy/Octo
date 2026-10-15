import argparse
import asyncio

from src.api.auth.auth_manager import AuthManager
from src.db.postgres.init_db import postgres_lifespan
from src.db.postgres.manager import PostgresManager


async def create_admin(email: str, password: str) -> int:
    async with postgres_lifespan() as (_, session_factory):
        user = await PostgresManager(session_factory).upsert_user(
                email=email, hashed_password=AuthManager.get_password_hash(password)
        )
    print(f"admin user ready: \nid={user.id} \nemail={user.email}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create (or reset the password of) the admin user")
    parser.add_argument("--email", default="admin@octo.local")
    parser.add_argument("--password", default="admin")
    args = parser.parse_args()
    return asyncio.run(create_admin(args.email, args.password))


if __name__ == "__main__":
    raise SystemExit(main())
