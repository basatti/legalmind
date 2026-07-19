"""LEG-51: update review model and add threaded feedback table

Revision ID: c1d2e3f4a5b6
Revises: dd761b9ccc7b
Create Date: 2026-07-20 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "dd761b9ccc7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    # --- 1. Update review table -------------------------------------------
    # The existing review table has: id, case_id, reviewer_id, comments
    # We need to: add created_at, make comments nullable (it's set after review)

    op.add_column(
        "review",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Make comments nullable — reviewer may add it later, not at creation
    op.alter_column("review", "comments", nullable=True)

    # Add index on case_id for fast "all reviews for a case" queries
    op.create_index("ix_review_case_id", "review", ["case_id"])

    # --- 2. Create feedback table (threaded comments tree) -----------------
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column(
            "content", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["author_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["feedback.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["review.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_feedback_review_id", "feedback", ["review_id"])
    op.create_index("ix_feedback_parent_id", "feedback", ["parent_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_feedback_parent_id", table_name="feedback")
    op.drop_index("ix_feedback_review_id", table_name="feedback")
    op.drop_table("feedback")
    op.drop_index("ix_review_case_id", table_name="review")
    op.alter_column("review", "comments", nullable=False)
    op.drop_column("review", "created_at")
