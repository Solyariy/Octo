from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Response
from pydantic import Field
from starlette import status

from src.api.auth.dependencies import CurrentUserDep
from src.api.dependencies import (
    AiohttpClientDep,
    PostgresManagerDep,
    QdrantManagerDep,
)
from src.api.schemas import InputPost
from src.services.omni_pipeline import OmniPipeline
from src.services.schemas import ProcessingAccepted
from src.utils.annotations import StrUUID
from src.utils.logs import Logger
from src.utils.order import get_log_id

main_router = APIRouter()


@main_router.get("/health", status_code=status.HTTP_200_OK)
async def get_health():
    return dict(ok=True)


@main_router.post("/save", response_model=list[StrUUID])
async def post_save(
        posts: Annotated[list[InputPost], Field(min_length=1)],
        user_info: CurrentUserDep,
        pg_manager: PostgresManagerDep,
) -> list[StrUUID]:
    Logger.info(
        "Saving posts",
        user_id=str(user_info.id),
        count=len(posts),
        platforms=sorted(
            {
                p.platform
                for p in posts
            }
        ),
    )
    inserted = await pg_manager.insert_posts_bulk(posts, user_info)
    return [str(p.id) for p in inserted]


@main_router.post(
    "/process/all",
    response_model=ProcessingAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_process_all(
        response: Response,
        background_tasks: BackgroundTasks,
        user_info: CurrentUserDep,
        pg_manager: PostgresManagerDep,
        qdrant_manager: QdrantManagerDep,
        aiohttp_client: AiohttpClientDep,
) -> ProcessingAccepted:
    posts = await pg_manager.claim_pending_posts(user_id=user_info.id)
    accepted = ProcessingAccepted(log_id=get_log_id(), post_ids=[str(p.id) for p in posts])
    if not posts:
        Logger.info("No pending posts to process", user_id=str(user_info.id))
        response.status_code = status.HTTP_200_OK
        return accepted

    pipeline = OmniPipeline(
        pg_manager=pg_manager, qdrant_manager=qdrant_manager, aiohttp_client=aiohttp_client
    )
    background_tasks.add_task(pipeline.run, posts, user_info)
    Logger.info("Processing scheduled", user_id=str(user_info.id), posts=len(posts))
    return accepted
