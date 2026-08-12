"""drop the dead rolepermission table

The permission matrix has two definitions and only one of them runs.

`foundation/permissions.py` holds `ROLE_PERMISSIONS`, an 11-permission matrix
that every router and service imports and that `frontend/lib/permissions.ts`
mirrors. The `rolepermission` table holds a different, 6-permission matrix that
nothing in `src/` has ever read, seeded by revision 126d6a6790ee.

They disagree about the actual rules. The table gives attorney `case:write`, a
permission that exists nowhere in the running system; it withholds
`case:read:assigned` from partner and `case:edit:assigned` from paralegal, both
of which they really have. So inspecting the database to answer "who can do
what" returns a wrong answer, which has already happened once on this project.

The sharper hazard is the name. `foundation.models.Permission` and
`foundation.permissions.Permission` are two different enums with the same name,
and the models one exists only to type this table's column. A future
`from foundation.models import Permission` would type-check clean under
`mypy --strict`, resolve `Permission.CASE_WRITE` happily, and authorize against
a permission no role holds.

Deleting rather than reviving it: this matrix is security-critical, and rules in
code get code review, tests and rollback, while rules in a table get an UPDATE
statement. The table has never been the source of truth, so nothing is lost.

The `role` enum type is deliberately NOT dropped -- it is shared with
`user.role`. Only the `permission` type goes, which this table's column was the
sole user of.

Revision ID: d246df291c3c
Revises: 856d25abda07
Create Date: 2026-08-11 20:26:41.208764

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d246df291c3c"
down_revision: str | Sequence[str] | None = "856d25abda07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The matrix as 126d6a6790ee seeded it. Reproduced here only so `downgrade`
# restores exactly what it removed -- this is not, and never was, the live one.
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
    """Remove the table, its index, and the enum type only it used."""
    op.drop_index("ix_role_permission_role", table_name="rolepermission")
    op.drop_table("rolepermission")

    # Dropped after the table, since the column depends on the type. `role` is
    # left alone -- `user.role` still uses it.
    postgresql.ENUM(name="permission").drop(op.get_bind())


def downgrade() -> None:
    """Put back exactly what 126d6a6790ee created, seed rows included."""
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
