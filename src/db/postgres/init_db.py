from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.settings import db_settings

my_metadata = MetaData()


class Base(DeclarativeBase):
    metadata = my_metadata


def get_base_metadata() -> MetaData:
    from src.db.postgres import models  # noqa: F401  (registers tables on my_metadata)
    return my_metadata


@asynccontextmanager
async def postgres_lifespan() -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    """App-scoped engine: build once at startup, dispose once at shutdown.

    Importing this module must never open a connection — `alembic/env.py` imports
    it to reach `get_base_metadata()` while running over psycopg2, and an engine
    left undisposed raises "Event loop is closed" during interpreter teardown.
    """
    engine = create_async_engine(
        db_settings.POSTGRES_URL,
        echo=db_settings.POSTGRES_ECHO,
        pool_size=db_settings.POSTGRES_POOL_SIZE,
        max_overflow=db_settings.POSTGRES_MAX_OVERFLOW,
        pool_timeout=db_settings.POSTGRES_POOL_TIMEOUT,
        pool_recycle=db_settings.POSTGRES_POOL_RECYCLE,
        pool_pre_ping=db_settings.POSTGRES_POOL_PRE_PING,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        # create_async_engine connects lazily, so probe eagerly: without this a bad
        # POSTGRES_URL only surfaces on the first request instead of at startup.
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        yield engine, session_factory
    finally:
        await engine.dispose()
