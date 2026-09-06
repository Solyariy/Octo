"""add is_processed to media_files

Revision ID: 8936081c845a
Revises: d7f7ce457a08
Create Date: 2026-09-06 21:09:39.028463

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8936081c845a'
down_revision: Union[str, Sequence[str], None] = 'd7f7ce457a08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'media_files',
        sa.Column('is_processed', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('media_files', 'is_processed')
