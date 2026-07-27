"""leg13 add ingestion job table

Revision ID: 495e4a37f3b4
Revises: a4b805a11065
Create Date: 2026-07-27 12:15:36.004273

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '495e4a37f3b4'
down_revision: Union[str, Sequence[str], None] = 'a4b805a11065'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ingestionjob",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "done", "failed", name="ingestionstatus"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestionjob_document_id", "ingestionjob", ["document_id"], unique=False)
    op.create_index("ix_ingestionjob_status", "ingestionjob", ["status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_ingestionjob_status", table_name="ingestionjob")
    op.drop_index("ix_ingestionjob_document_id", table_name="ingestionjob")
    op.drop_table("ingestionjob")
    sa.Enum(name="ingestionstatus").drop(op.get_bind(), checkfirst=True)
