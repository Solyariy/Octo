from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from src.settings import db_settings

engine = create_async_engine(db_settings.POSTGRES_URL, echo=False)

postgres_async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_postgres_client() -> AsyncSession:
    async with postgres_async_session() as session:
        yield session


my_metadata = MetaData()


class Base(DeclarativeBase):
    metadata = my_metadata


def get_base_metadata():
    from src.db.postgres import models
    return my_metadata
