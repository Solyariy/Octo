import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer
from starlette import status

from src.api.dependencies import get_current_user
from src.api.schemas import InputMediaFile
from src.db.postgres.init_db import postgres_async_session
from src.db.postgres.manager import PostgresManager
from src.db.postgres.schemas import UserInfo, MediaFile
from src.db.qdrant.manager import QdrantManager
from src.embedders.factory import get_embedding_manager
from src.embedders.models import EmbeddersEnum
from src.embedders.tests.nvidia_cosmos import download_video
from src.utils.annotations import StrUUID
from src.utils.order import get_uuid_str

main_router = APIRouter()


@main_router.get(
    "/health",
    status_code=status.HTTP_200_OK
)
async def get_health():
    return dict(ok=True)


@main_router.post(
    "/save",
    response_model=list[StrUUID]
)
async def post_save(
        data_all: list[InputMediaFile],
        bg: BackgroundTasks,
        user_info: UserInfo = Depends(get_current_user),
) -> list[StrUUID]:
    pg_manager = PostgresManager()
    media_files: list[MediaFile] = await pg_manager.insert_media_file_bulk(data_all)
    #
    # async def bg_task(data_: list[InputMediaFile]):
    #     paths = [
    #         download_video(data.url, Path(tempfile.gettempdir()) / get_uuid_str())
    #         for data in data_
    #     ]
    #     with get_embedding_manager(EmbeddersEnum.COSMOS_EMBED1_448P) as manager:
    #         video_embeddings = manager.encode_video(paths)
    #
    #     await QdrantManager().upsert_vectors(
    #         embedder_info=EmbeddersEnum.COSMOS_EMBED1_448P,
    #         vectors=video_embeddings
    #     )
    # bg.add_task(bg_task, data_all)
    return [str(m.id) for m in media_files]


@main_router.post(
    "/process/all",
    status_code=status.HTTP_201_CREATED
)
async def post_process_all(
        user_info: UserInfo = Depends(get_current_user)
):
    paths = [
        download_video(data.url, Path(tempfile.gettempdir()) / get_uuid_str())
        for data in data_
    ]
    with get_embedding_manager(EmbeddersEnum.COSMOS_EMBED1_448P) as manager:
        video_embeddings = manager.encode_video(paths)

    await QdrantManager().upsert_vectors(
        embedder_info=EmbeddersEnum.COSMOS_EMBED1_448P,
        vectors=video_embeddings
    )
