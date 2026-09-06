from pydantic import BaseModel


class InputMediaFile(BaseModel):
    url: str
