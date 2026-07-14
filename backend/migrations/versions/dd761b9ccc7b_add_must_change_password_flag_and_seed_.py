"""add must change password flag and seed first admin

Revision ID: dd761b9ccc7b
Revises: 126d6a6790ee
Create Date: 2026-07-13 13:00:26.337154

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd761b9ccc7b"
down_revision: str | Sequence[str] | None = "126d6a6790ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# bcrypt hash of the temporary password "ChangeMe123!"
SEED_ADMIN_PASSWORD_HASH = "$2b$12$dscePn0wQlONmDYwqOMa0eYk2eoslYFrrzuG8F8R9AHjRMdXbgF0m"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    # Seed the first admin so the bootstrap problem is solved: without this,
    # no one could log in to create any other user.
    op.execute(
        f"""
        INSERT INTO "user" (email, full_name, hashed_password, role, is_active, must_change_password, created_at)
        VALUES (
            'admin@legalmind.local',
            'System Administrator',
            '{SEED_ADMIN_PASSWORD_HASH}',
            'admin',
            true,
            true,
            now()
        )
        ON CONFLICT (email) DO NOTHING
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM \"user\" WHERE email = 'admin@legalmind.local'")
    op.drop_column("user", "must_change_password")
    