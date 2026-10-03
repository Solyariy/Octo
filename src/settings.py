from contextvars import ContextVar
from datetime import timedelta
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LOG_ID = ContextVar("LOG_ID")


class MainSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ROOT_PATH: Path = Path(__file__).parent.parent.resolve()
    MODELS_PATH: Path = ROOT_PATH / "models"
    TEMP_DIR_PATH: Path = ROOT_PATH / "temp"
    INSTAGRAM_TEMP_DIR_PATH: Path = TEMP_DIR_PATH / "instagram"
    THREADS_TEMP_DIR_PATH: Path = TEMP_DIR_PATH / "threads"

    HF_AUTH_TOKEN: SecretStr

    SECRET_KEY: SecretStr
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: Annotated[
        timedelta,
        BeforeValidator(
            lambda v: timedelta(minutes=int(v)) if str(v).isdigit() else v
        ),
    ]


main_settings = MainSettings()


class DBSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_PREFER_GRPC: bool = False
    QDRANT_API_KEY: SecretStr | None = None
    QDRANT_TIMEOUT: int = 30
    # None leaves the client default (3 for the gRPC channel pool).
    QDRANT_POOL_SIZE: int | None = None
    QDRANT_CHECK_COMPATIBILITY: bool = True

    POSTGRES_URL: str = "postgresql+asyncpg://octo:octo@localhost:5432/octo"
    POSTGRES_ECHO: bool = False
    # Pools are per worker process: with `gunicorn -w N` the ceiling against
    # Postgres is N * (POSTGRES_POOL_SIZE + POSTGRES_MAX_OVERFLOW).
    POSTGRES_POOL_SIZE: int = 10
    POSTGRES_MAX_OVERFLOW: int = 0
    POSTGRES_POOL_TIMEOUT: int = 30
    POSTGRES_POOL_RECYCLE: int = 1800
    # compose restarts Postgres out from under pooled connections.
    POSTGRES_POOL_PRE_PING: bool = True


db_settings = DBSettings()
