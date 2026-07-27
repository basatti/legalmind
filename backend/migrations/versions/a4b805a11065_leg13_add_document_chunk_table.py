"""leg13 add document chunk table

Revision ID: a4b805a11065
Revises: a5decc8cad6a
Create Date: 2026-07-27 11:09:15.815078

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'a4b805a11065'
down_revision: Union[str, Sequence[str], None] = 'a5decc8cad6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Deliberately a literal, not imported from foundation.models. A migration is a
# snapshot of history — if the model's dimension changes later, this file must
# still describe what it originally created.
EMBEDDING_DIMENSIONS = 1024


def upgrade() -> None:
    """Upgrade schema."""
    # Switches pgvector on for this database. Kept here rather than run by hand
    # so it also happens for teammates and in CI.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documentchunk",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["case.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_documentchunk_document_id", "documentchunk", ["document_id"])
    op.create_index("ix_documentchunk_case_id", "documentchunk", ["case_id"])
    op.create_index(
        "ix_documentchunk_document_sequence",
        "documentchunk",
        ["document_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_documentchunk_document_sequence", table_name="documentchunk")
    op.drop_index("ix_documentchunk_case_id", table_name="documentchunk")
    op.drop_index("ix_documentchunk_document_id", table_name="documentchunk")
    op.drop_table("documentchunk")
    # The extension is deliberately left in place — dropping it would fail if
    # anything else has come to use a vector column.
