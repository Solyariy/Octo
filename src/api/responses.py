from fastapi_pagination import Page
from fastapi_pagination.customization import CustomizedPage, UseIncludeTotal, UseName
from pydantic import BaseModel

from src.db.postgres.schemas import Post
from src.enums import Modality


class SearchHit(BaseModel):
    """One post ranked by its best-matching point (caption, image or video)."""

    post: Post
    score: float
    modality: Modality
    media_index: int


# No total: every point "matches" a semantic query, so a count would be meaningless.
SearchPage = CustomizedPage[Page[SearchHit], UseIncludeTotal(include_total=False), UseName("SearchPage")]
