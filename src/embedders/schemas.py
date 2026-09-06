from pydantic import BaseModel, Field

from src.utils.annotations import StrUUID
from src.utils.order import get_uuid_str


class CustomVector(BaseModel):
    id: StrUUID = Field(default_factory=get_uuid_str)
    vector: list[float]
