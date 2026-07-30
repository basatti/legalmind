"""add document chunk model

Revision ID: 09108df8f690
Revises: 6778f92d81bd
Create Date: 2026-07-30 12:52:06.999368
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "09108df8f690"
down_revision: Union[str, Sequence[str], None] = "6778f92d81bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the document_chunk table."""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunk",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "page_number",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "sequence",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "text",
            sa.String(),
            nullable=False,
        ),
        sa.Column(
            "embedding",
            Vector(1024),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["case.id"],
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_document_chunk_case_id",
        "document_chunk",
        ["case_id"],
        unique=False,
    )

    op.create_index(
        "ix_document_chunk_document_id",
        "document_chunk",
        ["document_id"],
        unique=False,
    )

    op.create_index(
        "uq_document_chunk_document_sequence",
        "document_chunk",
        ["document_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    """Remove the document_chunk table."""

    op.drop_index(
        "uq_document_chunk_document_sequence",
        table_name="document_chunk",
    )

    op.drop_index(
        "ix_document_chunk_document_id",
        table_name="document_chunk",
    )

    op.drop_index(
        "ix_document_chunk_case_id",
        table_name="document_chunk",
    )

    op.drop_table("document_chunk")
