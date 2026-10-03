from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from src.api.auth.auth_manager import AuthManager
from src.api.dependencies import PostgresManagerDep
from src.db.postgres.schemas import UserInfo

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_current_user(
        token: Annotated[str, Depends(oauth2_scheme)], pg_manager: PostgresManagerDep
) -> UserInfo:
    return await AuthManager.get_current_user(token=token, pg_manager=pg_manager)


CurrentUserDep = Annotated[UserInfo, Depends(get_current_user)]
