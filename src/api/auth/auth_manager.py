from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from starlette import status

from src.api.auth.schemas import Token, TokenData
from src.db.postgres.manager import PostgresManager
from src.db.postgres.schemas import UserInfo
from src.settings import main_settings


class AuthManager:
    HASHER = PasswordHash.recommended()

    def __init__(self, pg_manager: PostgresManager):
        self.pg_manager = pg_manager

    @classmethod
    def create_access_token(
            cls,
            data: dict,
            expires_delta: timedelta = main_settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    ):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
                to_encode,
                main_settings.SECRET_KEY.get_secret_value(),
                algorithm=main_settings.ALGORITHM,
        )
        return encoded_jwt

    @classmethod
    def verify_password(cls, plain_password, hashed_password):
        return cls.HASHER.verify(plain_password, hashed_password)

    @classmethod
    def get_password_hash(cls, password):
        return cls.HASHER.hash(password)

    @staticmethod
    async def get_current_user(token: str, pg_manager: PostgresManager) -> UserInfo:
        credentials_exception = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(
                    token,
                    main_settings.SECRET_KEY.get_secret_value(),
                    algorithms=[main_settings.ALGORITHM],
            )
            user_id = payload.get("sub")
            if user_id is None:
                raise credentials_exception
            token_data = TokenData(user_id=user_id)
        except InvalidTokenError as e:
            raise credentials_exception from e
        user = await pg_manager.get_user_by_id(user_id=token_data.user_id)
        if user is None:
            raise credentials_exception
        return user

    @classmethod
    async def authenticate_user(cls, email: str, password: str, pg_manager: PostgresManager) -> Token:
        pg_user = await pg_manager.get_user_for_auth(user_email=email)
        is_valid = cls.verify_password(password, pg_user.hashed_password)
        if not is_valid:
            raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect username or password",
                    headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = cls.create_access_token(data={"sub": email})
        return Token(access_token=access_token, token_type="bearer")
