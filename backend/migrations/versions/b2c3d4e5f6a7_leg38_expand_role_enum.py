"""LEG-38: expand role enum to admin/partner/attorney/paralegal

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ROLES = ("admin", "user")
NEW_ROLES = ("admin", "partner", "attorney", "paralegal")


def upgrade() -> None:
    """Expand the role enum from 2 values to 4."""
    # Postgres doesn't allow modifying enums in place cleanly,
    # so we use a temp text column to move data through.
    op.add_column("user", sa.Column("role_text", sa.Text(), nullable=True))

    op.execute('UPDATE "user" SET role_text = role::text')

    op.drop_column("user", "role")

    sa.Enum(*OLD_ROLES, name="role").drop(op.get_bind())

    new_enum = sa.Enum(*NEW_ROLES, name="role")
    new_enum.create(op.get_bind())

    op.add_column(
        "user",
        sa.Column(
            "role",
            sa.Enum(*NEW_ROLES, name="role"),
            nullable=False,
            server_default="attorney",
        ),
    )

    op.execute(
        """
        UPDATE "user"
        SET role = CASE role_text
            WHEN 'admin' THEN 'admin'
            WHEN 'user'  THEN 'attorney'
            ELSE 'attorney'
        END::role
        """
    )

    op.drop_column("user", "role_text")
    op.alter_column("user", "role", server_default=None)


def downgrade() -> None:
    """Revert role enum back to admin/user."""
    op.add_column("user", sa.Column("role_text", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE "user"
        SET role_text = CASE role::text
            WHEN 'admin'    THEN 'admin'
            ELSE 'user'
        END
        """
    )

    op.drop_column("user", "role")

    sa.Enum(*NEW_ROLES, name="role").drop(op.get_bind())

    old_enum = sa.Enum(*OLD_ROLES, name="role")
    old_enum.create(op.get_bind())

    op.add_column(
        "user",
        sa.Column(
            "role",
            sa.Enum(*OLD_ROLES, name="role"),
            nullable=False,
            server_default="user",
        ),
    )

    op.execute('UPDATE "user" SET role = role_text::role')

    op.drop_column("user", "role_text")
    op.alter_column("user", "role", server_default=None)
