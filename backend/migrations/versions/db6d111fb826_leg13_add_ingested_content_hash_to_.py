"""leg13 add ingested content hash to document

Revision ID: db6d111fb826
Revises: 495e4a37f3b4
Create Date: <leave whatever was generated>

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'db6d111fb826'
down_revision: Union[str, Sequence[str], None] = '495e4a37f3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable on purpose: existing documents have never been ingested, and NULL
    # is how we say that. They will be filled in the first time each one runs.
    op.add_column("document", sa.Column("ingested_content_hash", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("document", "ingested_content_hash")
