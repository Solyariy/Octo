from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi_pagination import Params
from starlette import status

from src.api.auth.dependencies import CurrentUserDep
from src.api.dependencies import (
    AiohttpClientDep,
    EmbedderDep,
    PostgresManagerDep,
    QdrantManagerDep,
)
from src.api.responses import TaskPage
from src.db.postgres.schemas import TaskDetail
from src.enums import ProcessingStatus
from src.services.omni_pipeline import OmniPipeline
from src.services.schemas import ProcessingAccepted
from src.utils.logs import Logger
from src.utils.order import get_log_id

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])

TASK_NOT_FOUND = "Task not found"


@tasks_router.get("", response_model=TaskPage)
async def list_tasks(
    user_info: CurrentUserDep,
    pg_manager: PostgresManagerDep,
    params: Annotated[Params, Depends()],
) -> TaskPage:
    """The caller's tasks, newest first, with per-task counts and derived status."""
    raw = params.to_raw_params().as_limit_offset()
    items, total = await pg_manager.list_tasks(
        user_id=user_info.id,
        limit=raw.limit,
        offset=raw.offset,
    )
    return TaskPage.create(
        items,
        params=params,
        total=total,
    )


@tasks_router.get("/{task_id}", response_model=TaskDetail)
async def get_task(
    task_id: UUID,
    user_info: CurrentUserDep,
    pg_manager: PostgresManagerDep,
) -> TaskDetail:
    """One task with every post and its outcome (status, failed stage, error) in this task."""
    task = await pg_manager.get_task_detail(user_id=user_info.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=TASK_NOT_FOUND)
    return task


@tasks_router.post(
    "/{task_id}/retry",
    response_model=ProcessingAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_task(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    user_info: CurrentUserDep,
    pg_manager: PostgresManagerDep,
    qdrant_manager: QdrantManagerDep,
    aiohttp_client: AiohttpClientDep,
    embedder: EmbedderDep,
) -> ProcessingAccepted:
    """Re-run the task's posts that failed and are still `FAILED`, as a new task."""
    task = await pg_manager.get_task(user_id=user_info.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=TASK_NOT_FOUND)
    if task.status != ProcessingStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only failed tasks can be retried; this one is {task.status}",
        )

    log_id = get_log_id()
    new_task_id, posts = await pg_manager.claim_failed_task_posts(
        user_id=user_info.id,
        task_id=task_id,
        request_id=log_id,
    )
    if not posts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No failed posts left to retry",
        )

    pipeline = OmniPipeline(
        pg_manager=pg_manager,
        qdrant_manager=qdrant_manager,
        aiohttp_client=aiohttp_client,
        embedder=embedder,
    )
    background_tasks.add_task(
        pipeline.run,
        new_task_id,
        posts,
        user_info,
    )
    Logger.info(
        "Retry scheduled",
        user_id=str(user_info.id),
        retry_of=str(task_id),
        task_id=str(new_task_id),
        posts=len(posts),
    )
    return ProcessingAccepted(
        log_id=log_id,
        task_id=str(new_task_id),
        post_ids=[str(p.id) for p in posts],
    )
