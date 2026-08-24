import uuid
from datetime import datetime, UTC
from zoneinfo import ZoneInfo

from src.settings import LOG_ID, main_settings
from src.utils.annotations import StrUUID


def get_model_path(name: str):
    return main_settings.MODELS_PATH / name


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


def get_datetime_kyiv() -> datetime:
    return datetime.now(ZoneInfo("Europe/Kyiv"))


def get_uuid_str() -> StrUUID:
    return str(uuid.uuid4())


def get_log_id() -> StrUUID:
    id_ = LOG_ID.get(None)
    if not id_:
        id_ = get_uuid_str()
        LOG_ID.set(id_)
    return id_
