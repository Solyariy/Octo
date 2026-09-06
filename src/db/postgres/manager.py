import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.api.schemas import InputMediaFile
from src.db.postgres.init_db import postgres_async_session
from src.db.postgres.models import UserPostgres, MediaFilePostgres
from src.db.postgres.schemas import UserInfo, MediaFile
from src.utils.annotations import StrUUID
from src.utils.logs import LoggerMixin


class PostgresManager(LoggerMixin):
    _limiter = asyncio.Semaphore(10)

    async def __exec(self, stmt, commit: bool) -> Any:
        async with self._limiter, postgres_async_session() as session:
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

    async def insert_media_file_bulk(self, media_files: list[InputMediaFile]) -> list[MediaFile]:
        stmt = (insert(MediaFilePostgres)
                .values([mf.model_dump(mode="json") for mf in media_files])
                .on_conflict_do_nothing()
                .returning(MediaFilePostgres))
        res = await self.__exec(stmt, commit=True)
        return [
            MediaFile.model_validate(r)
            for r in res.scalars()
        ]
