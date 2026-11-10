import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.schemas import InputPost
from src.db.postgres.models import (
    PostPostgres,
    ScraperStatusPostgres,
    TaskPostgres,
    TaskPostPostgres,
    UserPostgres,
)
from src.db.postgres.schemas import (
    Post,
    PostIdUrl,
    ScraperStatus,
    Task,
    TaskDetail,
    TaskPost,
    UserInfo,
)
from src.enums import Platform, ProcessingStatus
from src.utils.annotations import StrUUID
from src.utils.logs import LoggerMixin


class PostgresManager(LoggerMixin):
    """One short-lived session per statement, drawn from the app-scoped pool.

    Concurrency is capped by the engine pool (POSTGRES_POOL_SIZE), not by a
    semaphore of its own: an `asyncio.Semaphore` binds permanently to whichever
    event loop first contends on it, which breaks any later `asyncio.run()` in
    the same process.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def __exec(self, stmt, commit: bool) -> Any:
        async with self._session_factory() as session:
            try:
                response = await session.execute(stmt)
            except Exception as e:
                await session.rollback()
                self.log_error("Statement execution failed", error=e)
                raise

            if commit:
                try:
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    self.log_error("Commit failed", error=e)
                    raise

            return response

    async def get_user_by_id(self, user_id: StrUUID) -> UserInfo:
        stmt = select(UserPostgres).where(UserPostgres.id == user_id)
        res = await self.__exec(stmt, commit=False)
        user = res.scalar_one()
        user = UserInfo.model_validate(user)
        return user

    async def get_user_by_email(self, user_email: str) -> UserInfo:
        stmt = select(UserPostgres).where(UserPostgres.email == user_email)
        res = await self.__exec(stmt, commit=False)
        user = res.scalar_one()
        user = UserInfo.model_validate(user)
        return user

    async def get_user_for_auth(self, user_email: str) -> UserPostgres:
        stmt = select(UserPostgres).where(UserPostgres.email == user_email)
        res = await self.__exec(stmt, commit=False)
        user = res.scalar_one()
        return user

    async def upsert_user(self, email: str, hashed_password: str) -> UserInfo:
        stmt = (
            insert(UserPostgres)
            .values(email=email, hashed_password=hashed_password)
            .on_conflict_do_update(
                index_elements=[UserPostgres.email],
                set_={"hashed_password": hashed_password},
            )
            .returning(UserPostgres)
        )
        res = await self.__exec(stmt, commit=True)
        return UserInfo.model_validate(res.scalar_one())

    async def insert_posts_bulk(self, posts: list[InputPost], user_info: UserInfo) -> list[Post]:
        """Insert as `PENDING`; urls that already exist are skipped and absent from the result."""
        stmt = (
            insert(PostPostgres)
            .values(
                [
                    {
                        "url": post.url,
                        "platform": post.platform,
                        "status": ProcessingStatus.PENDING,
                        "user_id": user_info.id,
                    }
                    for post in posts
                ]
            )
            .on_conflict_do_nothing()
            .returning(PostPostgres)
        )
        res = await self.__exec(stmt, commit=True)
        inserted = [Post.model_validate(r) for r in res.scalars()]
        self.log_info(
            "Posts inserted",
            user_id=str(user_info.id),
            received=len(posts),
            inserted=len(inserted),
            skipped_duplicates=len(posts) - len(inserted),
        )
        return inserted

    async def claim_pending_posts(
        self,
        user_id: StrUUID,
        request_id: str,
    ) -> tuple[UUID | None, list[Post]]:
        """Atomically move the user's `PENDING` posts to `IN_PROCESS` and record them as a task.

        One `UPDATE ... RETURNING`, so concurrent callers can never claim the same row.
        A non-empty claim inserts its `tasks` + `task_posts` rows in the same transaction.
        Returns `(task_id, posts)`; `task_id` is None when nothing was pending.
        """
        stmt = (
            update(PostPostgres)
            .where(
                PostPostgres.user_id == user_id,
                PostPostgres.status == ProcessingStatus.PENDING,
            )
            .values(status=ProcessingStatus.IN_PROCESS)
            .returning(PostPostgres)
        )
        return await self._claim_as_task(
            stmt,
            user_id,
            request_id,
        )

    async def claim_failed_task_posts(
        self,
        user_id: StrUUID,
        task_id: StrUUID,
        request_id: str,
    ) -> tuple[UUID | None, list[Post]]:
        """Re-claim the posts that failed in `task_id` and are still `FAILED`, as a new task.

        Posts that succeeded since (or were claimed by a concurrent retry) are skipped by the
        `status = FAILED` guard. Returns `(new_task_id, posts)`; None when nothing is left.
        """
        failed_in_task = select(TaskPostPostgres.post_id).where(
            TaskPostPostgres.task_id == task_id,
            TaskPostPostgres.status == ProcessingStatus.FAILED,
        )
        stmt = (
            update(PostPostgres)
            .where(
                PostPostgres.user_id == user_id,
                PostPostgres.status == ProcessingStatus.FAILED,
                PostPostgres.id.in_(failed_in_task),
            )
            .values(status=ProcessingStatus.IN_PROCESS)
            .returning(PostPostgres)
        )
        return await self._claim_as_task(
            stmt,
            user_id,
            request_id,
            retry_of=str(task_id),
        )

    async def _claim_as_task(
        self,
        claim_stmt,
        user_id: StrUUID,
        request_id: str,
        **log_context,
    ) -> tuple[UUID | None, list[Post]]:
        """Run a claiming `UPDATE ... RETURNING` and record a non-empty claim as a task."""
        task_id = None
        async with self._session_factory() as session:
            try:
                res = await session.execute(claim_stmt)
                claimed = [Post.model_validate(r) for r in res.scalars()]
                if claimed:
                    task_id = uuid.uuid4()
                    await session.execute(
                        insert(TaskPostgres).values(
                            id=task_id,
                            request_id=request_id,
                            user_id=user_id,
                        )
                    )
                    await session.execute(
                        insert(TaskPostPostgres).values(
                            [
                                {
                                    "task_id": task_id,
                                    "post_id": p.id,
                                    "status": ProcessingStatus.IN_PROCESS,
                                }
                                for p in claimed
                            ]
                        )
                    )
                await session.commit()
            except Exception as e:
                await session.rollback()
                self.log_error(
                    "Claiming posts failed",
                    error=e,
                    request_id=request_id,
                    **log_context,
                )
                raise

        self.log_info(
            "Posts claimed",
            user_id=str(user_id),
            request_id=request_id,
            task_id=str(task_id) if task_id else None,
            count=len(claimed),
            post_ids=[str(p.id) for p in claimed],
            **log_context,
        )
        return task_id, claimed

    async def finish_task(
        self,
        task_id: StrUUID,
        succeeded: list[UUID],
        failures: dict[UUID, tuple[str, str]],
    ) -> None:
        """Persist a task's outcome in one transaction: post statuses, per-task outcomes, counts.

        `failures` maps post id to `(stage, error)`.
        """
        async with self._session_factory() as session:
            try:
                for ids, status in (
                    (succeeded, ProcessingStatus.SUCCESS),
                    (list(failures), ProcessingStatus.FAILED),
                ):
                    if ids:
                        await session.execute(
                            update(PostPostgres)
                            .where(PostPostgres.id.in_(ids))
                            .values(status=status)
                        )
                rows = [
                    {
                        "task_id": task_id,
                        "post_id": post_id,
                        "status": ProcessingStatus.SUCCESS,
                        "stage": None,
                        "error": None,
                    }
                    for post_id in succeeded
                ] + [
                    {
                        "task_id": task_id,
                        "post_id": post_id,
                        "status": ProcessingStatus.FAILED,
                        "stage": stage,
                        "error": error,
                    }
                    for post_id, (stage, error) in failures.items()
                ]
                if rows:
                    # ORM bulk UPDATE by primary key (task_id, post_id).
                    await session.execute(update(TaskPostPostgres), rows)
                await session.execute(
                    update(TaskPostgres)
                    .where(TaskPostgres.id == task_id)
                    .values(success_count=len(succeeded), failed_count=len(failures))
                )
                await session.commit()
            except Exception as e:
                await session.rollback()
                self.log_error(
                    "Finishing task failed",
                    error=e,
                    task_id=str(task_id),
                )
                raise
        self.log_info(
            "Task finished",
            task_id=str(task_id),
            succeeded=len(succeeded),
            failed=len(failures),
        )

    @staticmethod
    def _task_select():
        total = (
            select(func.count())
            .where(TaskPostPostgres.task_id == TaskPostgres.id)
            .correlate(TaskPostgres)
            .scalar_subquery()
            .label("total_count")
        )
        return select(TaskPostgres, total)

    @staticmethod
    def _to_task(task: TaskPostgres, total_count: int) -> Task:
        return Task(
            id=task.id,
            request_id=task.request_id,
            user_id=task.user_id,
            created_at=task.created_at,
            total_count=total_count,
            success_count=task.success_count,
            failed_count=task.failed_count,
        )

    async def list_tasks(
        self,
        user_id: StrUUID,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        """The user's tasks, newest first, plus the user's total task count."""
        stmt = (
            self._task_select()
            .where(TaskPostgres.user_id == user_id)
            .order_by(TaskPostgres.created_at.desc(), TaskPostgres.id)
            .limit(limit)
            .offset(offset)
        )
        res = await self.__exec(stmt, commit=False)
        items = [self._to_task(task, total) for task, total in res.all()]
        count_stmt = select(func.count()).where(TaskPostgres.user_id == user_id)
        total = (await self.__exec(count_stmt, commit=False)).scalar_one()
        return items, total

    async def get_task(self, user_id: StrUUID, task_id: StrUUID) -> Task | None:
        """The task, or None when it does not exist or belongs to another user."""
        stmt = self._task_select().where(
            TaskPostgres.id == task_id,
            TaskPostgres.user_id == user_id,
        )
        res = await self.__exec(stmt, commit=False)
        row = res.one_or_none()
        return self._to_task(*row) if row is not None else None

    async def get_task_detail(self, user_id: StrUUID, task_id: StrUUID) -> TaskDetail | None:
        """The task with every post and its outcome in this task; None like `get_task`."""
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if task is None:
            return None
        stmt = (
            select(TaskPostPostgres, PostPostgres)
            .join(PostPostgres, PostPostgres.id == TaskPostPostgres.post_id)
            .where(TaskPostPostgres.task_id == task_id)
            .order_by(PostPostgres.created_at, PostPostgres.id)
        )
        res = await self.__exec(stmt, commit=False)
        posts = [
            TaskPost(
                post=Post.model_validate(post),
                status=task_post.status,
                stage=task_post.stage,
                error=task_post.error,
            )
            for task_post, post in res.all()
        ]
        return TaskDetail(**task.model_dump(exclude={"status"}), posts=posts)

    async def get_post(self, user_id: StrUUID, post_id: StrUUID) -> Post | None:
        """The post, or None when it does not exist or belongs to another user."""
        stmt = select(PostPostgres).where(
            PostPostgres.id == post_id,
            PostPostgres.user_id == user_id,
        )
        res = await self.__exec(stmt, commit=False)
        row = res.scalar_one_or_none()
        return Post.model_validate(row) if row is not None else None

    async def get_posts_by_ids(self, user_id: StrUUID, ids: list[StrUUID]) -> dict[UUID, Post]:
        """The user's posts among `ids`, keyed by id; ids of other users' posts are dropped."""
        if not ids:
            return {}
        stmt = select(PostPostgres).where(
            PostPostgres.id.in_(ids),
            PostPostgres.user_id == user_id,
        )
        res = await self.__exec(stmt, commit=False)
        return {row.id: Post.model_validate(row) for row in res.scalars()}

    async def get_posts_by_status(self, status: ProcessingStatus) -> list[Post]:
        """Every user's posts in `status`; maintenance use (e.g. `cli.qdrant_backfill`)."""
        stmt = select(PostPostgres).where(PostPostgres.status == status)
        res = await self.__exec(stmt, commit=False)
        return [Post.model_validate(row) for row in res.scalars()]

    async def get_media_file_by_id_bulk(self, ids: list[StrUUID]) -> list[PostIdUrl]:
        stmt = select(PostPostgres.id, PostPostgres.url).where(PostPostgres.id.in_(ids))
        res = await self.__exec(stmt, commit=False)
        return [PostIdUrl.model_validate(r) for r in res.all()]

    async def upsert_scraper_status(
        self,
        platform: Platform,
        status: ProcessingStatus,
    ) -> ScraperStatus:
        """Record the outcome of the platform's latest scraper request (one row per platform)."""
        stmt = (
            insert(ScraperStatusPostgres)
            .values(platform=platform, last_request_status=status)
            .on_conflict_do_update(
                index_elements=[ScraperStatusPostgres.platform],
                set_={"last_request_status": status, "updated_at": func.now()},
            )
            .returning(ScraperStatusPostgres)
        )
        res = await self.__exec(stmt, commit=True)
        return ScraperStatus.model_validate(res.scalar_one())
