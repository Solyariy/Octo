from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException
from starlette import status

from src.db.postgres.init_db import get_postgres_client
from src.db.postgres.manager import PostgresManager
from src.db.postgres.schemas import UserInfo
from src.utils.annotations import StrUUID
from src.utils.logs import Logger


async def get_current_user(
        user_id: StrUUID,
) -> UserInfo:
    try:
        user = await PostgresManager().get_user_by_id(user_id=user_id)
        return user
    except Exception as e:
        Logger.error(
            "Error on auth",
            user_id=user_id,
            error=e
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized",
        )
