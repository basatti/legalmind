"""Permission definitions and role → permission matrix.

Permission checks use set membership:
    required_permission in role_permissions(user.role)  →  O(1)

The permission matrix is a DAG / partial order:
    Admin ⊃ Partner ⊃ {Attorney, Paralegal}

Each role's permission set is explicit — no inheritance chain to resolve,
just a dict lookup + set intersection. This keeps auth checks O(1).
"""

from enum import StrEnum

from foundation.models import Role

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


class Permission(StrEnum):
    # Case read access
    CASE_READ_ANY = "case:read:any"  # can read all cases
    CASE_READ_ASSIGNED = "case:read:assigned"  # can only read assigned cases

    # Case write access
    CASE_CREATE = "case:create"
    CASE_EDIT_ANY = "case:edit:any"
    CASE_EDIT_ASSIGNED = "case:edit:assigned"
    CASE_DELETE = "case:delete"

    # Workflow transitions
    CASE_SUBMIT_FOR_REVIEW = "case:submit_for_review"  # Attorney only
    CASE_ASSIGN = "case:assign"  # Partner only
    CASE_REVIEW = "case:review"  # Partner only
    CASE_CLOSE = "case:close"  # Partner only

    # User management
    USER_MANAGE = "user:manage"  # Admin only


# ---------------------------------------------------------------------------
# Permission matrix  (role → frozenset of permissions)
#
# frozenset is hashable and immutable — permission checks are O(1) lookups.
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(
        [
            Permission.CASE_READ_ANY,
            Permission.CASE_READ_ASSIGNED,
            Permission.CASE_CREATE,
            Permission.CASE_EDIT_ANY,
            Permission.CASE_EDIT_ASSIGNED,
            Permission.CASE_DELETE,
            Permission.CASE_SUBMIT_FOR_REVIEW,
            Permission.CASE_ASSIGN,
            Permission.CASE_REVIEW,
            Permission.CASE_CLOSE,
            Permission.USER_MANAGE,
        ]
    ),
    Role.PARTNER: frozenset(
        [
            Permission.CASE_READ_ANY,  # Partners can read ALL cases
            Permission.CASE_READ_ASSIGNED,
            Permission.CASE_CREATE,
            Permission.CASE_EDIT_ANY,
            Permission.CASE_EDIT_ASSIGNED,
            Permission.CASE_ASSIGN,  # Partner-only
            Permission.CASE_REVIEW,  # Partner-only
            Permission.CASE_CLOSE,  # Partner-only
        ]
    ),
    Role.ATTORNEY: frozenset(
        [
            Permission.CASE_READ_ASSIGNED,  # can ONLY read assigned cases
            Permission.CASE_EDIT_ASSIGNED,
            Permission.CASE_SUBMIT_FOR_REVIEW,  # Attorney-only
        ]
    ),
    Role.PARALEGAL: frozenset(
        [
            Permission.CASE_READ_ASSIGNED,  # can ONLY read assigned cases
            Permission.CASE_EDIT_ASSIGNED,
        ]
    ),
}


def get_permissions(role: Role) -> frozenset[Permission]:
    """Return the permission set for a given role. O(1) dict lookup."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: Role, permission: Permission) -> bool:
    """Check if a role has a specific permission. O(1) set membership."""
    return permission in get_permissions(role)


def has_any_permission(role: Role, permissions: set[Permission]) -> bool:
    """Check if a role has at least one of the given permissions.

    Uses set intersection — O(min(len(a), len(b))).
    """
    return bool(get_permissions(role) & permissions)
