"use client";

import { useAuth } from "@/lib/auth";
import { hasAnyPermission, hasPermission } from "@/lib/permissions";
import type { Permission } from "@/lib/permissions";

/**
 * Hook that checks if the current user has a specific permission.
 *
 * Returns false if the user is not logged in.
 * The server is still the real gate — this is UI-only.
 *
 * Usage:
 *   const canAssign = usePermission("case:assign");
 *   if (canAssign) { ... }
 */
export function usePermission(permission: Permission): boolean {
  const { user } = useAuth();
  if (!user) return false;
  return hasPermission(user.role, permission);
}

/**
 * Hook that checks if the current user has ANY of the given permissions.
 *
 * Usage:
 *   const canEdit = useAnyPermission(["case:edit:any", "case:edit:assigned"]);
 */
export function useAnyPermission(permissions: Permission[]): boolean {
  const { user } = useAuth();
  if (!user) return false;
  return hasAnyPermission(user.role, permissions);
}
