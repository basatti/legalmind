/**
 * Frontend permission definitions — mirrors backend permissions.py exactly.
 *
 * The server is the real security gate. These are used only to show/hide
 * UI elements so users don't see actions they can't perform. A 403 from
 * the backend is always the authoritative rejection.
 */

import type { Role } from "@/types/api";

// ---------------------------------------------------------------------------
// Permissions
// ---------------------------------------------------------------------------

export type Permission =
  | "case:read:any"
  | "case:read:assigned"
  | "case:create"
  | "case:edit:any"
  | "case:edit:assigned"
  | "case:delete"
  | "case:submit_for_review"
  | "case:assign"
  | "case:review"
  | "case:close"
  | "user:manage";

// ---------------------------------------------------------------------------
// Permission matrix — role → set of permissions
// Must stay in sync with backend ROLE_PERMISSIONS dict.
// ---------------------------------------------------------------------------

const ROLE_PERMISSIONS: Record<Role, ReadonlySet<Permission>> = {
  admin: new Set<Permission>([
    "case:read:any",
    "case:read:assigned",
    "case:create",
    "case:edit:any",
    "case:edit:assigned",
    "case:delete",
    "case:submit_for_review",
    "case:assign",
    "case:review",
    "case:close",
    "user:manage",
  ]),
  partner: new Set<Permission>([
    "case:read:any",
    "case:read:assigned",
    "case:create",
    "case:edit:any",
    "case:edit:assigned",
    "case:assign",
    "case:review",
    "case:close",
  ]),
  attorney: new Set<Permission>([
    "case:read:assigned",
    "case:edit:assigned",
    "case:submit_for_review",
  ]),
  paralegal: new Set<Permission>([
    "case:read:assigned",
    "case:edit:assigned",
  ]),
};

// ---------------------------------------------------------------------------
// Utility functions — O(1) set membership checks
// ---------------------------------------------------------------------------

export function hasPermission(role: Role, permission: Permission): boolean {
  return ROLE_PERMISSIONS[role].has(permission);
}

export function hasAnyPermission(
  role: Role,
  permissions: Permission[]
): boolean {
  return permissions.some((p) => ROLE_PERMISSIONS[role].has(p));
}
