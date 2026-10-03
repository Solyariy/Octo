from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.schemas import InputMediaFile
from src.db.postgres.models import MediaFilePostgres, UserPostgres
from src.db.postgres.schemas import MediaFile, UserInfo
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

    async def insert_media_file_bulk(self, media_files: list[InputMediaFile]) -> list[MediaFile]:
        stmt = (
                insert(MediaFilePostgres).values(
                        [mf.model_dump(mode="json") for mf in media_files]
                ).on_conflict_do_nothing().returning(MediaFilePostgres)
        )
        res = await self.__exec(stmt, commit=True)
        return [MediaFile.model_validate(r) for r in res.scalars()]

    async def get_unprocessed_media_files(self, user_id: StrUUID) -> list[MediaFile]:
        stmt = (
                select(MediaFilePostgres).where(MediaFilePostgres.user_id == user_id
                                                ).where(MediaFilePostgres.is_processed == False)
        )
        res = await self.__exec(stmt, commit=False)
        return [MediaFile.model_validate(r) for r in res.scalars()]

    async def set_processed_true(self, ids: list[StrUUID]):
        stmt = (
                update(MediaFilePostgres).where(MediaFilePostgres.id.in_(ids)
                                                ).values(is_processed=True)
        )
        await self.__exec(stmt, commit=True)
