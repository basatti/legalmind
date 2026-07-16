"""add documents table

Revision ID: c47a5224069d
Revises: dd761b9ccc7b
Create Date: 2026-07-16 12:19:32.045792

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c47a5224069d'
down_revision: Union[str, Sequence[str], None] = 'dd761b9ccc7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("document", sa.Column("case_id", sa.Integer(), nullable=True))
    op.add_column("document", sa.Column("filename", sa.String(), nullable=True))
    op.add_column("document", sa.Column("uploaded_by", sa.Integer(), nullable=True))
    op.add_column("document", sa.Column("uploaded_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(None, "document", "case", ["case_id"], ["id"])
    op.create_foreign_key(None, "document", "user", ["uploaded_by"], ["id"])
    op.create_index("ix_document_case_id", "document", ["case_id"])
    op.drop_column("document", "title")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("document", sa.Column("title", sa.String(), nullable=False, server_default=""))
    op.drop_index("ix_document_case_id", table_name="document")
    op.drop_column("document", "uploaded_at")
    op.drop_column("document", "uploaded_by")
    op.drop_column("document", "filename")
    op.drop_column("document", "case_id")
    