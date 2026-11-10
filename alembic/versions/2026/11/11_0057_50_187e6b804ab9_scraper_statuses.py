"""scraper_statuses

Revision ID: 187e6b804ab9
Revises: d1903b160a6e
Create Date: 2026-11-11 00:57:50.818632

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "187e6b804ab9"
down_revision: Union[str, Sequence[str], None] = "d1903b160a6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Both types exist already (init revision); reuse them rather than CREATE TYPE again.
platform = postgresql.ENUM(
    "threads",
    "instagram",
    "youtube",
    name="platform",
    create_type=False,
)
processing_status = postgresql.ENUM(
    "pending",
    "in_process",
    "success",
    "failed",
    name="processingstatus",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    # The new value is not used inside this transaction, which PG 12+ allows.
    op.execute("ALTER TYPE platform ADD VALUE IF NOT EXISTS 'youtube'")
    op.create_table(
        "scraper_statuses",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "platform",
            platform,
            nullable=False,
        ),
        sa.Column(
            "last_request_status",
            processing_status,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="scraper_statuses_pkey"),
        sa.UniqueConstraint("platform", name="scraper_statuses_platform_key"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("scraper_statuses")
    # Postgres cannot drop an enum value, so 'youtube' stays in the `platform` type.
