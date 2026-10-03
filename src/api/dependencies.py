from typing import Annotated

import aiohttp
from fastapi import Depends, Request

from src.db.postgres.manager import PostgresManager
from src.db.qdrant.manager import QdrantManager


async def get_aiohttp_client(request: Request) -> aiohttp.ClientSession:
    return request.app.state.aiohttp_client


async def get_qdrant_manager(request: Request) -> QdrantManager:
    return QdrantManager(request.app.state.qdrant_client)


async def get_postgres_manager(request: Request) -> PostgresManager:
    return PostgresManager(request.app.state.postgres_sessionmaker)


AiohttpClientDep = Annotated[aiohttp.ClientSession, Depends(get_aiohttp_client)]
QdrantManagerDep = Annotated[QdrantManager, Depends(get_qdrant_manager)]
PostgresManagerDep = Annotated[PostgresManager, Depends(get_postgres_manager)]

# async def get_current_user(
#         user_id: StrUUID,
#         pg_manager: PostgresManagerDep,
# ) -> UserInfo:
#     try:
#         user = await pg_manager.get_user_by_id(user_id=user_id)
#         return user
#     except Exception as e:
#         Logger.error(
#             "Error on auth",
#             user_id=user_id,
#             error=e
#         )
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Not authorized",
#         )

# CurrentUserDep = Annotated[UserInfo, Depends(get_current_user)]
