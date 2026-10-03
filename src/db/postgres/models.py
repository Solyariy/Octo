import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, false, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.postgres.init_db import Base


class UserPostgres(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
            PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(unique=True)
    hashed_password: Mapped[str]


class MediaFilePostgres(Base):
    __tablename__ = "media_files"

    id: Mapped[uuid.UUID] = mapped_column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            default=uuid.uuid4,
    )
    url: Mapped[str] = mapped_column(unique=True)
    is_processed: Mapped[bool] = mapped_column(default=False, server_default=false())
    user_id: Mapped[uuid.UUID] = mapped_column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id"),
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
