"""add permissions and role permission matrix

Revision ID: 126d6a6790ee
Revises: b2c3d4e5f6a7
Create Date: 2026-07-13 11:56:02.791669

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "126d6a6790ee"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("admin", "partner", "attorney", "paralegal")

PERMISSIONS = (
    "case:read:any",
    "case:read:assigned",
    "case:write",
    "case:assign",
    "case:review",
    "case:submit",
)

ROLE_PERMISSION_MATRIX: dict[str, list[str]] = {
    "admin": [
        "case:read:any",
        "case:read:assigned",
        "case:write",
        "case:assign",
        "case:review",
        "case:submit",
    ],
    "partner": [
        "case:read:any",
        "case:write",
        "case:assign",
        "case:review",
    ],
    "attorney": [
        "case:read:assigned",
        "case:write",
        "case:submit",
    ],
    "paralegal": [
        "case:read:assigned",
    ],
}


def upgrade() -> None:
    """Upgrade schema."""
    permission_enum = postgresql.ENUM(*PERMISSIONS, name="permission")
    permission_enum.create(op.get_bind())

    op.create_table(
        "rolepermission",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(*ROLES, name="role", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "permission",
            postgresql.ENUM(*PERMISSIONS, name="permission", create_type=False),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_role_permission_role", "rolepermission", ["role"])

    for role, permissions in ROLE_PERMISSION_MATRIX.items():
        for permission in permissions:
            op.execute(
                f"""
                INSERT INTO rolepermission (role, permission)
                VALUES ('{role}', '{permission}')
                """
            )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_role_permission_role", table_name="rolepermission")
    op.drop_table("rolepermission")
    op.execute("DROP TYPE permission")
    