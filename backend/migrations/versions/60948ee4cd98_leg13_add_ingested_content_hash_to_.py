"""leg13 add ingested content hash to document

Revision ID: 60948ee4cd98
Revises: 9b39f87e2df8
Create Date: 2026-07-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "60948ee4cd98"
down_revision: str | Sequence[str] | None = "9b39f87e2df8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable on purpose: existing documents have never been ingested, and NULL
    # is how we say that. They will be filled in the first time each one runs.
    op.add_column("document", sa.Column("ingested_content_hash", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("document", "ingested_content_hash")
