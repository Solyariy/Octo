"""task_posts

Revision ID: d1903b160a6e
Revises: b274b5e5f7c5
Create Date: 2026-11-10 23:18:07.809924

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1903b160a6e"
down_revision: Union[str, Sequence[str], None] = "b274b5e5f7c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Created by the init revision; reuse it rather than CREATE TYPE again.
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
    op.create_table(
        "task_posts",
        sa.Column(
            "task_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "post_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "status",
            processing_status,
            nullable=False,
        ),
        sa.Column(
            "stage",
            sa.String(),
            nullable=True,
        ),
        sa.Column(
            "error",
            sa.Text(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name="task_posts_post_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name="task_posts_task_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "task_id",
            "post_id",
            name="task_posts_pkey",
        ),
    )
    op.create_index(
        op.f("ix_task_posts_post_id"),
        "task_posts",
        ["post_id"],
        unique=False,
    )
    op.add_column(
        "tasks",
        sa.Column(
            "success_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "failed_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    # Backfill: each task's claimed posts, with the post's current status as its outcome.
    op.execute(
        """
        INSERT INTO task_posts (task_id, post_id, status)
        SELECT DISTINCT t.id, p.id, p.status
        FROM tasks t
        CROSS JOIN LATERAL unnest(t.post_ids) AS u(post_id)
        JOIN posts p ON p.id = u.post_id
        """
    )
    op.execute(
        """
        UPDATE tasks t SET
            success_count = (
                SELECT count(*) FROM task_posts tp
                WHERE tp.task_id = t.id AND tp.status = 'success'
            ),
            failed_count = (
                SELECT count(*) FROM task_posts tp
                WHERE tp.task_id = t.id AND tp.status = 'failed'
            )
        """
    )
    op.drop_column("tasks", "post_ids")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "tasks",
        sa.Column(
            "post_ids",
            postgresql.ARRAY(sa.UUID()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE tasks t SET post_ids = COALESCE(
            (SELECT array_agg(tp.post_id) FROM task_posts tp WHERE tp.task_id = t.id),
            '{}'
        )
        """
    )
    op.alter_column(
        "tasks",
        "post_ids",
        server_default=None,
    )
    op.drop_column("tasks", "failed_count")
    op.drop_column("tasks", "success_count")
    op.drop_index(op.f("ix_task_posts_post_id"), table_name="task_posts")
    op.drop_table("task_posts")
