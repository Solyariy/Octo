import asyncio
import threading
import time
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import aiofiles.tempfile
import aiohttp

from src.db.postgres.manager import PostgresManager
from src.db.postgres.schemas import Post, UserInfo
from src.db.qdrant.manager import QdrantManager
from src.db.qdrant.models import get_collection
from src.db.qdrant.schemas import QdrantVector
from src.embedders.factory import get_embedding_manager
from src.embedders.models import EmbeddersEnum
from src.enums import Modality, ProcessingStatus
from src.link_scrapers.manager import LinkScraper
from src.services.schemas import EmbeddingItem, PipelineStage, PostJob
from src.settings import main_settings
from src.utils.basic import download_and_save_file
from src.utils.logs import LoggerMixin

# Serialises model use across concurrent runs so two requests never hold two copies of the
# model. A threading.Lock does not bind to an event loop, unlike asyncio.Semaphore.
_EMBED_LOCK = threading.Lock()

_KNOWN_SUFFIXES = {
    Modality.IMAGE: ({".jpg", ".jpeg", ".png", ".webp", ".heic"}, ".jpg"),
    Modality.VIDEO: ({".mp4", ".mov", ".webm", ".mkv"}, ".mp4"),
}


def _media_suffix(url: str, modality: Modality) -> str:
    known, default = _KNOWN_SUFFIXES[modality]
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in known else default


def _describe(error: BaseException | str) -> str:
    return error if isinstance(error, str) else f"{type(error).__name__}: {error}"


class OmniPipeline(LoggerMixin):
    """Scrape -> download -> embed (one call) -> upsert to Qdrant -> set post status.

    Takes posts already claimed as `IN_PROCESS`. Failures are isolated per post: a post stops
    at its first failed stage and the rest continue. A stage-wide failure (embedding, upsert)
    fails every post still active. Every claimed post ends `SUCCESS` or `FAILED`.
    """

    EMBEDDER = EmbeddersEnum.GEMMA2_OMNI

    def __init__(
            self,
            pg_manager: PostgresManager,
            qdrant_manager: QdrantManager,
            aiohttp_client: aiohttp.ClientSession,
    ):
        self.pg_manager = pg_manager
        self.qdrant_manager = qdrant_manager
        self.aiohttp_client = aiohttp_client
        self.link_scraper = LinkScraper(aiohttp_client)

    async def run(self, posts: list[Post], user_info: UserInfo) -> None:
        """Never raises: it runs as a background task, so every outcome ends up in logs and DB."""
        jobs = [PostJob(post=post) for post in posts]
        started = time.perf_counter()
        self.log_info(
            "Pipeline started",
            user_id=str(user_info.id),
            posts=len(jobs),
            embedder=self.EMBEDDER.value,
        )
        vectors: list[QdrantVector] = []
        try:
            async with self._stage(PipelineStage.SCRAPE, jobs):
                await self._scrape(jobs)

            main_settings.TEMP_DIR_PATH.mkdir(parents=True, exist_ok=True)
            async with aiofiles.tempfile.TemporaryDirectory(
                    dir=main_settings.TEMP_DIR_PATH,
                    prefix="omni_"
            ) as temp_dir:
                async with self._stage(PipelineStage.DOWNLOAD, jobs):
                    await self._download(jobs, Path(temp_dir))
                async with self._stage(PipelineStage.EMBED, jobs):
                    vectors = await self._embed(jobs)

            async with self._stage(PipelineStage.STORE, jobs):
                await self._store(jobs, vectors, user_info)
        except Exception as e:
            self.log_error("Pipeline crashed outside a stage", error=e)
            for job in self._active(jobs):
                self._fail(job, PipelineStage.FINALIZE, e)
        finally:
            await self._finalize(jobs, started)

    # --- stages ---------------------------------------------------------------------------

    async def _scrape(self, jobs: list[PostJob]) -> None:
        active = self._active(jobs)
        results = await self.link_scraper.scrap_bulk([job.post.url for job in active])
        for job, result in zip(active, results, strict=True):
            if isinstance(result, BaseException):
                self._fail(job, PipelineStage.SCRAPE, result)
                continue
            if not (result.text or result.image_urls or result.video_urls):
                self._fail(job, PipelineStage.SCRAPE, "empty_post: no text, images or videos")
                continue
            job.scraped = result
            if result.text:
                job.items.append(self._item(job, Modality.TEXT, 0, result.text))
            self.log_info(
                "Post scraped",
                post_id=str(job.post.id),
                platform=job.post.platform,
                has_text=bool(result.text),
                images=len(result.image_urls),
                videos=len(result.video_urls),
            )

    async def _download(self, jobs: list[PostJob], temp_dir: Path) -> None:
        targets: list[tuple[PostJob, Modality, int, str, Path]] = []
        for job in self._active(jobs):
            for modality, urls in (
                    (Modality.IMAGE, job.scraped.image_urls),
                    (Modality.VIDEO, job.scraped.video_urls),
            ):
                for index, url in enumerate(urls):
                    name = f"{job.post.id}_{modality}_{index:02d}{_media_suffix(url, modality)}"
                    targets.append((job, modality, index, url, temp_dir / name))

        results = await asyncio.gather(
            *[
                download_and_save_file(
                    url=url,
                    destination=destination,
                    aiohttp_client=self.aiohttp_client
                ) for _, _, _, url, destination in targets
            ],
            return_exceptions=True,
        )

        downloaded: Counter[str] = Counter()
        for (job, modality, index, url, destination), result in zip(targets, results, strict=True):
            if isinstance(result, BaseException):
                if job.is_active:
                    self._fail(job, PipelineStage.DOWNLOAD, result, url=url, modality=modality)
                continue
            local_paths = (
                job.scraped.image_local_paths
                if modality == Modality.IMAGE else job.scraped.video_local_paths
            )
            local_paths.append(str(destination))
            job.items.append(self._item(job, modality, index, str(destination)))
            downloaded[str(job.post.id)] += 1

        for job in self._active(jobs):
            self.log_info(
                "Post media downloaded",
                post_id=str(job.post.id),
                files=downloaded[str(job.post.id)],
                bytes=sum(Path(p).stat().st_size for p in job.scraped.image_local_paths) +
                      sum(Path(p).stat().st_size for p in job.scraped.video_local_paths),
            )

    async def _embed(self, jobs: list[PostJob]) -> list[QdrantVector]:
        items = [item for job in self._active(jobs) for item in job.items]
        if not items:
            return []
        self.log_info(
            "Embedding batch",
            items=len(items),
            by_modality=dict(Counter(str(item.modality) for item in items)),
        )
        inputs = [(item.modality, item.content) for item in items]

        def encode():
            with _EMBED_LOCK, get_embedding_manager(self.EMBEDDER) as manager:
                return manager.encode_inputs(inputs)

        # to_thread copies the context, so the manager's logs keep this request's log_id.
        embeddings = await asyncio.to_thread(encode)
        return [
            QdrantVector(
                post_id=str(item.post_id),
                platform=item.platform,
                modality=item.modality,
                media_index=item.media_index,
                vector=embedding,
            ) for item, embedding in zip(items, embeddings, strict=True)
        ]

    async def _store(
            self, jobs: list[PostJob], vectors: list[QdrantVector], user_info: UserInfo,
    ) -> None:
        if not vectors:
            return
        await self.qdrant_manager.upsert_vectors(
            collection=get_collection(self.EMBEDDER), vectors=vectors, user_info=user_info
        )
        # Every active job reached this point with at least one embedded item.
        for job in self._active(jobs):
            job.stored = True

    async def _finalize(self, jobs: list[PostJob], started: float) -> None:
        for job in jobs:
            if not job.stored and job.is_active:
                self._fail(job, PipelineStage.FINALIZE, "interrupted before vectors were stored")
        succeeded = [job.post.id for job in jobs if job.stored]
        failed = [job.post.id for job in jobs if not job.stored]
        try:
            await self.pg_manager.set_status(succeeded, ProcessingStatus.SUCCESS)
            await self.pg_manager.set_status(failed, ProcessingStatus.FAILED)
        except Exception as e:
            self.log_error(
                "Could not persist post statuses; rows stay in_process",
                error=e,
                post_ids=[str(job.post.id) for job in jobs],
            )
        self.log_info(
            "Pipeline finished",
            total=len(jobs),
            succeeded=len(succeeded),
            failed=len(failed),
            failed_by_stage=dict(
                Counter(str(job.failed_stage) for job in jobs if job.failed_stage)
            ),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )

    # --- helpers --------------------------------------------------------------------------

    @asynccontextmanager
    async def _stage(self, stage: PipelineStage, jobs: list[PostJob]) -> AsyncIterator[None]:
        """Log the stage's span; a stage-wide exception fails every post still active."""
        active_before = len(self._active(jobs))
        started = time.perf_counter()
        self.log_info("Stage started", stage=stage, active_posts=active_before)
        try:
            yield
        except Exception as e:
            self.log_error("Stage failed", error=e, stage=stage, active_posts=active_before)
            for job in self._active(jobs):
                self._fail(job, stage, e)
        active_after = len(self._active(jobs))
        self.log_info(
            "Stage finished",
            stage=stage,
            active_posts=active_after,
            failed_in_stage=active_before - active_after,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def _active(jobs: list[PostJob]) -> list[PostJob]:
        return [job for job in jobs if job.is_active]

    @staticmethod
    def _item(job: PostJob, modality: Modality, index: int, content: str) -> EmbeddingItem:
        return EmbeddingItem(
            post_id=job.post.id,
            platform=job.post.platform,
            modality=modality,
            media_index=index,
            content=content,
        )

    def _fail(
            self, job: PostJob, stage: PipelineStage, error: BaseException | str, **context,
    ) -> None:
        job.failed_stage = stage
        job.error = _describe(error)
        self.log_warning(
            "Post failed",
            post_id=str(job.post.id),
            url=job.post.url,
            platform=job.post.platform,
            stage=stage,
            reason=job.error,
            error=error if isinstance(error, BaseException) else None,
            **context,
        )
