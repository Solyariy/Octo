from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from src.api.auth.auth_manager import AuthManager
from src.api.auth.dependencies import CurrentUserDep
from src.api.auth.schemas import Token
from src.api.dependencies import PostgresManagerDep
from src.db.postgres.schemas import UserInfo

auth_router = APIRouter()


@auth_router.post("/token")
async def login_for_access_token(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()], pg_manager: PostgresManagerDep
) -> Token:
    return await AuthManager.authenticate_user(
            email=form_data.username, password=form_data.password, pg_manager=pg_manager
    )


@auth_router.get("/users/me/")
async def read_users_me(current_user: CurrentUserDep) -> UserInfo:
    return current_user
