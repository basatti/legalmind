"""merge leg48 documents into review branch

Revision ID: a5decc8cad6a
Revises: 0bff4770f6b8, c47a5224069d
Create Date: 2026-07-27 11:07:01.680275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5decc8cad6a'
down_revision: Union[str, Sequence[str], None] = ('0bff4770f6b8', 'c47a5224069d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
