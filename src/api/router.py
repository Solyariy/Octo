import asyncio
from pathlib import Path

import aiofiles
import aiohttp
from fastapi import APIRouter, BackgroundTasks, Response
from fastapi.params import Depends
from qdrant_client import AsyncQdrantClient
from starlette import status

from src.api.dependencies import get_current_user, get_aiohttp_client, get_qdrant_client
from src.api.schemas import InputMediaFile
from src.db.postgres.init_db import postgres_async_session
from src.db.postgres.manager import PostgresManager
from src.db.postgres.schemas import UserInfo, MediaFile
from src.db.qdrant.manager import QdrantManager
from src.embedders.factory import get_embedding_manager
from src.embedders.models import EmbeddersEnum
from src.embedders.tests.nvidia_cosmos import download_video
from src.settings import main_settings
from src.utils.annotations import StrUUID
from src.utils.basic import download_and_save_file
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
    status_code=status.HTTP_200_OK
)
async def post_process_all(
        user_info: UserInfo = Depends(get_current_user),
        aiohttp_client: aiohttp.ClientSession = Depends(get_aiohttp_client),
        qdrant_client: AsyncQdrantClient = Depends(get_qdrant_client)
):
    pg_manager = PostgresManager()
    unprocessed_data = await pg_manager.get_unprocessed_media_files(user_id=user_info.id)
    if not unprocessed_data:
        return Response(status_code=status.HTTP_200_OK)
    async with aiofiles.tempfile.TemporaryDirectory(
            prefix=str(main_settings.TEMP_DIR_PATH) + "/"
    ) as temp_dir:
        paths = await asyncio.gather(*[
            download_and_save_file(
                url=data.url,
                destination=Path(temp_dir) / f"{get_uuid_str()}.mp4",
                aiohttp_client=aiohttp_client
            )
            for data in unprocessed_data
        ])

        def one_(paths_):
            with get_embedding_manager(EmbeddersEnum.COSMOS_EMBED1_448P) as manager:
                ve = manager.encode_video(paths_)
                return ve

        video_embeddings = await asyncio.to_thread(one_, paths)
    await QdrantManager(qdrant_client).upsert_vectors(
        embedder_info=EmbeddersEnum.COSMOS_EMBED1_448P,
        vectors=video_embeddings
    )
    await pg_manager.set_processed_true(ids=[data.id for data in unprocessed_data])
    return Response(status_code=status.HTTP_200_OK)
