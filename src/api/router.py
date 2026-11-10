import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi_filter import FilterDepends
from fastapi_pagination import Params
from pydantic import Field
from starlette import status

from src.api.auth.dependencies import CurrentUserDep
from src.api.dependencies import (
    AiohttpClientDep,
    EmbedderDep,
    PostgresManagerDep,
    QdrantManagerDep,
)
from src.api.responses import SearchHit, SearchPage
from src.api.schemas import InputPost
from src.api.tasks import tasks_router
from src.db.postgres.schemas import Post
from src.db.qdrant.filters import PointFilter
from src.db.qdrant.models import get_collection
from src.embedders.locks import EMBED_LOCK
from src.services.omni_pipeline import OmniPipeline
from src.services.schemas import ProcessingAccepted
from src.utils.annotations import StrUUID
from src.utils.logs import Logger
from src.utils.order import get_log_id

main_router = APIRouter()
main_router.include_router(tasks_router)

# Qdrant groups have no offset, so each page re-ranks everything before it; cap the depth.
SEARCH_MAX_DEPTH = 1000


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
        platforms=sorted({p.platform for p in posts}),
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
    embedder: EmbedderDep,
) -> ProcessingAccepted:
    log_id = get_log_id()
    task_id, posts = await pg_manager.claim_pending_posts(user_id=user_info.id, request_id=log_id)
    accepted = ProcessingAccepted(
        log_id=log_id,
        task_id=str(task_id) if task_id else None,
        post_ids=[str(p.id) for p in posts],
    )
    if not posts:
        Logger.info("No pending posts to process", user_id=str(user_info.id))
        response.status_code = status.HTTP_200_OK
        return accepted

    pipeline = OmniPipeline(
        pg_manager=pg_manager,
        qdrant_manager=qdrant_manager,
        aiohttp_client=aiohttp_client,
        embedder=embedder,
    )
    background_tasks.add_task(
        pipeline.run,
        task_id,
        posts,
        user_info,
    )
    Logger.info(
        "Processing scheduled",
        user_id=str(user_info.id),
        task_id=str(task_id),
        posts=len(posts),
    )
    return accepted


@main_router.get("/posts/{post_id}", response_model=Post)
async def get_post(
    post_id: UUID,
    user_info: CurrentUserDep,
    pg_manager: PostgresManagerDep,
) -> Post:
    post = await pg_manager.get_post(user_id=user_info.id, post_id=post_id)
    if post is None:
        # Same answer for "missing" and "someone else's", so ids leak nothing.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@main_router.get("/search", response_model=SearchPage)
async def get_search(
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=512,
            description="Text query",
        ),
    ],
    user_info: CurrentUserDep,
    pg_manager: PostgresManagerDep,
    qdrant_manager: QdrantManagerDep,
    embedder: EmbedderDep,
    point_filter: Annotated[PointFilter, FilterDepends(PointFilter)],
    params: Annotated[Params, Depends()],
) -> SearchPage:
    """Semantic search over the user's processed posts; filters apply inside Qdrant."""
    Logger.info(
        "Searching posts",
        user_id=str(user_info.id),
        query_chars=len(q),
        filters=point_filter.model_dump(mode="json", exclude_none=True),
    )

    def encode():
        with EMBED_LOCK:
            return embedder.encode_text([q], prompt_name="SearchQuery")[0]

    raw = params.to_raw_params().as_limit_offset()
    if raw.offset + raw.limit > SEARCH_MAX_DEPTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"page * size must not exceed {SEARCH_MAX_DEPTH}; narrow the filters instead",
        )

    query_vector = await asyncio.to_thread(encode)
    hits = await qdrant_manager.search_posts(
        collection=get_collection(OmniPipeline.EMBEDDER),
        query_vector=query_vector,
        user_info=user_info,
        point_filter=point_filter,
        limit=raw.limit,
        offset=raw.offset,
    )
    posts = await pg_manager.get_posts_by_ids(
        user_id=user_info.id, ids=[hit.post_id for hit in hits]
    )
    items = [
        SearchHit(
            post=posts[UUID(hit.post_id)],
            score=hit.score,
            modality=hit.modality,
            media_index=hit.media_index,
        )
        for hit in hits
        if UUID(hit.post_id) in posts
    ]
    return SearchPage.create(items, params=params)
