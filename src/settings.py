from pathlib import Path
from contextvars import ContextVar
from pydantic_settings import BaseSettings, SettingsConfigDict

LOG_ID = ContextVar("LOG_ID")


class MainSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MODELS_PATH: Path = Path(__name__).parent.parent.resolve() / "models"
    HF_AUTH_TOKEN: str


main_settings = MainSettings()
