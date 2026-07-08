"""LEG-35: update case status enum and add assignment indexes

Revision ID: a1b2c3d4e5f6
Revises: 6e3f90abf518
Create Date: 2026-07-08 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "6e3f90abf518"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Old and new enum values
OLD_STATUSES = ("OPEN", "IN_PROGRESS", "CLOSED")
NEW_STATUSES = (
    "draft",
    "in_progress",
    "submitted_for_review",
    "under_review",
    "revisions_requested",
    "closed",
)


def upgrade() -> None:
    """Upgrade schema."""
    # --- 1. Replace the casestatus enum with the full set of values --------
    # Postgres doesn't support removing enum values, so we:
    # a) add a temporary text column
    # b) copy status values across (mapping old → new)
    # c) drop the old enum column
    # d) create new enum type
    # e) add new column with the new enum type
    # f) populate from temp column
    # g) drop temp column

    op.add_column("case", sa.Column("status_text", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE "case"
        SET status_text = CASE status::text
            WHEN 'OPEN'        THEN 'draft'
            WHEN 'IN_PROGRESS' THEN 'in_progress'
            WHEN 'CLOSED'      THEN 'closed'
            ELSE 'draft'
        END
        """
    )

    op.drop_column("case", "status")

    new_enum = sa.Enum(*NEW_STATUSES, name="casestatus")
    new_enum.create(op.get_bind())

    op.add_column(
        "case",
        sa.Column(
            "status",
            sa.Enum(*NEW_STATUSES, name="casestatus"),
            nullable=False,
            server_default="draft",
        ),
    )

    op.execute(
        """
        UPDATE "case"
        SET status = status_text::casestatus
        """
    )

    op.drop_column("case", "status_text")

    # Remove server default now that data is populated
    op.alter_column("case", "status", server_default=None)

    # --- 2. Add indexes on assignment foreign keys -------------------------
    op.create_index("ix_assignment_case_id", "assignment", ["case_id"])
    op.create_index("ix_assignment_user_id", "assignment", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index("ix_assignment_user_id", table_name="assignment")
    op.drop_index("ix_assignment_case_id", table_name="assignment")

    # Revert casestatus enum back to old values
    op.add_column("case", sa.Column("status_text", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE "case"
        SET status_text = CASE status::text
            WHEN 'draft'                THEN 'OPEN'
            WHEN 'in_progress'          THEN 'IN_PROGRESS'
            WHEN 'submitted_for_review' THEN 'IN_PROGRESS'
            WHEN 'under_review'         THEN 'IN_PROGRESS'
            WHEN 'revisions_requested'  THEN 'IN_PROGRESS'
            WHEN 'closed'               THEN 'CLOSED'
            ELSE 'OPEN'
        END
        """
    )

    op.drop_column("case", "status")

    sa.Enum(*NEW_STATUSES, name="casestatus").drop(op.get_bind())

    old_enum = sa.Enum(*OLD_STATUSES, name="casestatus")
    old_enum.create(op.get_bind())

    op.add_column(
        "case",
        sa.Column(
            "status",
            sa.Enum(*OLD_STATUSES, name="casestatus"),
            nullable=False,
            server_default="OPEN",
        ),
    )

    op.execute(
        """
        UPDATE "case"
        SET status = status_text::casestatus
        """
    )

    op.drop_column("case", "status_text")
    op.alter_column("case", "status", server_default=None)
