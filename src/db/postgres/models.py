import uuid
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import func

from src.db.postgres.init_db import Base


class UserPostgres(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(unique=True)


class MediaFilePostgres(Base):
    __tablename__ = "media_files"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    url: Mapped[str] = mapped_column(unique=True)
    is_processed: Mapped[bool] = mapped_column(insert_default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
