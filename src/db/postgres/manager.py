from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.schemas import InputPost
from src.db.postgres.models import PostPostgres, UserPostgres
from src.db.postgres.schemas import Post, PostIdUrl, UserInfo
from src.enums import ProcessingStatus
from src.utils.annotations import StrUUID
from src.utils.logs import LoggerMixin


class PostgresManager(LoggerMixin):
    """One short-lived session per statement, drawn from the app-scoped pool.

    Concurrency is capped by the engine pool (POSTGRES_POOL_SIZE), not by a
    semaphore of its own: an `asyncio.Semaphore` binds permanently to whichever
    event loop first contends on it, which breaks any later `asyncio.run()` in
    the same process.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def __exec(self, stmt, commit: bool) -> Any:
        async with self._session_factory() as session:
            try:
                response = await session.execute(stmt)
            except Exception as e:
                await session.rollback()
                self.log_error("Statement execution failed", error=e)
                raise

            if commit:
                try:
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    self.log_error("Commit failed", error=e)
                    raise

            return response

    async def get_user_by_id(self, user_id: StrUUID) -> UserInfo:
        stmt = select(UserPostgres).where(UserPostgres.id == user_id)
        res = await self.__exec(stmt, commit=False)
        user = res.scalar_one()
        user = UserInfo.model_validate(user)
        return user

    async def get_user_by_email(self, user_email: str) -> UserInfo:
        stmt = select(UserPostgres).where(UserPostgres.email == user_email)
        res = await self.__exec(stmt, commit=False)
        user = res.scalar_one()
        user = UserInfo.model_validate(user)
        return user

    async def get_user_for_auth(self, user_email: str) -> UserPostgres:
        stmt = select(UserPostgres).where(UserPostgres.email == user_email)
        res = await self.__exec(stmt, commit=False)
        user = res.scalar_one()
        return user

    async def upsert_user(self, email: str, hashed_password: str) -> UserInfo:
        stmt = (
                insert(UserPostgres).values(email=email,
                                            hashed_password=hashed_password).on_conflict_do_update(
                                                    index_elements=[UserPostgres.email],
                                                    set_={
                                                            "hashed_password": hashed_password
                                                    },
                                            ).returning(UserPostgres)
        )
        res = await self.__exec(stmt, commit=True)
        return UserInfo.model_validate(res.scalar_one())

    async def insert_posts_bulk(self, posts: list[InputPost], user_info: UserInfo) -> list[Post]:
        """Insert as `PENDING`; urls that already exist are skipped and absent from the result."""
        stmt = (
                insert(PostPostgres).values(
                        [
                                {
                                        "url": post.url,
                                        "platform": post.platform,
                                        "status": ProcessingStatus.PENDING,
                                        "user_id": user_info.id,
                                } for post in posts
                        ]
                ).on_conflict_do_nothing().returning(PostPostgres)
        )
        res = await self.__exec(stmt, commit=True)
        inserted = [Post.model_validate(r) for r in res.scalars()]
        self.log_info(
                "Posts inserted",
                user_id=str(user_info.id),
                received=len(posts),
                inserted=len(inserted),
                skipped_duplicates=len(posts) - len(inserted),
        )
        return inserted

    async def claim_pending_posts(self, user_id: StrUUID) -> list[Post]:
        """Atomically move the user's `PENDING` posts to `IN_PROCESS` and return them.

        One `UPDATE ... RETURNING`, so concurrent callers can never claim the same row.
        """
        stmt = (
                update(PostPostgres).where(
                        PostPostgres.user_id == user_id,
                        PostPostgres.status == ProcessingStatus.PENDING,
                ).values(status=ProcessingStatus.IN_PROCESS).returning(PostPostgres)
        )
        res = await self.__exec(stmt, commit=True)
        claimed = [Post.model_validate(r) for r in res.scalars()]
        self.log_info(
                "Pending posts claimed",
                user_id=str(user_id),
                count=len(claimed),
                post_ids=[str(p.id) for p in claimed],
        )
        return claimed

    async def set_status(self, ids: list[StrUUID], status: ProcessingStatus) -> None:
        if not ids:
            return
        stmt = update(PostPostgres).where(PostPostgres.id.in_(ids)).values(status=status)
        await self.__exec(stmt, commit=True)
        self.log_info(
                "Post status updated",
                status=status,
                count=len(ids),
                post_ids=[str(i) for i in ids]
        )

    async def get_media_file_by_id_bulk(self, ids: list[StrUUID]) -> list[PostIdUrl]:
        stmt = select(PostPostgres.id, PostPostgres.url).where(PostPostgres.id.in_(ids))
        res = await self.__exec(stmt, commit=False)
        return [PostIdUrl.model_validate(r) for r in res.all()]
