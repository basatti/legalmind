"""drop obsolete feedback table before LEG-51 recreates it

The initial migration created a "feedback" table with just id/content/rating.
Nothing on main ever used it. LEG-51 later added a real threaded-feedback
"feedback" table (review_id/author_id/parent_id) without dropping this one
first, so upgrading a database from scratch fails with "relation feedback
already exists" once it reaches c1d2e3f4a5b6. Drop the placeholder here so
LEG-51 has a clean slate to build on.

Revision ID: d4e5f6a7b8c9
Revises: dd761b9ccc7b
Create Date: 2026-07-29 13:45:55.664527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'dd761b9ccc7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table("feedback")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
