"""fix seeded admin email to a resolvable TLD

Revision ID: 856d25abda07
Revises: 60948ee4cd98
Create Date: 2026-08-09 10:48:14.237513

dd761b9ccc7b seeded the bootstrap admin as `admin@legalmind.local`, which no
one can ever log in as: `.local` is a reserved special-use TLD, so `EmailStr`
rejects it during request validation and `/auth/login` answers 422 before the
password is looked at. On a fresh database that left no way into the system at
all — the seeded account exists and is unusable.

The address is only ever typed into a login form, never delivered to, so the
fix is simply a TLD that validates. `admin@legalmind.com` is what
`docs/running-locally.md` has documented all along.

dd761b9ccc7b is left untouched on purpose: it has already run everywhere, so
editing it would fix nothing that exists and would make the file disagree with
what was actually applied.

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "856d25abda07"
down_revision: str | Sequence[str] | None = "60948ee4cd98"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNUSABLE_EMAIL = "admin@legalmind.local"
SEED_ADMIN_EMAIL = "admin@legalmind.com"


def _rename(from_email: str, to_email: str) -> None:
    # Guarded by NOT EXISTS because `user.email` is unique: on a database where
    # someone already created the destination address by hand, an unguarded
    # UPDATE would abort the migration. Renaming nothing is the right outcome
    # there — a working admin account already exists.
    op.execute(
        f"""
        UPDATE "user"
        SET email = '{to_email}'
        WHERE email = '{from_email}'
          AND NOT EXISTS (
              SELECT 1 FROM "user" WHERE email = '{to_email}'
          )
        """
    )


def upgrade() -> None:
    """Upgrade schema."""
    _rename(UNUSABLE_EMAIL, SEED_ADMIN_EMAIL)


def downgrade() -> None:
    """Downgrade schema."""
    _rename(SEED_ADMIN_EMAIL, UNUSABLE_EMAIL)
