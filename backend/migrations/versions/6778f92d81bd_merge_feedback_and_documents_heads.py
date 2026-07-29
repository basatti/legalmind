"""merge feedback and documents heads

Revision ID: 6778f92d81bd
Revises: 0bff4770f6b8, c47a5224069d
Create Date: 2026-07-29 13:43:35.037067

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6778f92d81bd'
down_revision: Union[str, Sequence[str], None] = ('0bff4770f6b8', 'c47a5224069d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
