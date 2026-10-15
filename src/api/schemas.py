from pydantic import BaseModel


class InputPost(BaseModel):
    url: str


