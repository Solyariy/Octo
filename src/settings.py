from pathlib import Path
from contextvars import ContextVar

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LOG_ID = ContextVar("LOG_ID")


class MainSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MODELS_PATH: Path = Path(__name__).parent.parent.resolve() / "models"
    HF_AUTH_TOKEN: str

    SECRET_KEY: SecretStr
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int


main_settings = MainSettings()


class DBSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_PREFER_GRPC: bool = False

    POSTGRES_URL: str = "postgresql+asyncpg://octo:octo@localhost:5432/octo"


db_settings = DBSettings()
