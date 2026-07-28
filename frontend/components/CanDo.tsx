"use client";

import type { ReactNode } from "react";
import type { Permission } from "@/lib/permissions";
import { useAnyPermission, usePermission } from "@/lib/usePermission";

// ---------------------------------------------------------------------------
// <CanDo permission="case:assign"> — single permission gate
// ---------------------------------------------------------------------------

interface CanDoProps {
  permission: Permission;
  children: ReactNode;
  /** Optional fallback when permission is denied */
  fallback?: ReactNode;
}

/**
 * Renders children only if the current user has the given permission.
 * Renders fallback (or nothing) otherwise.
 *
 * The server is still the real gate — this is UI-only show/hide.
 *
 * Usage:
 *   <CanDo permission="case:assign">
 *     <button>Assign Case</button>
 *   </CanDo>
 */
export function CanDo({ permission, children, fallback = null }: CanDoProps) {
  const allowed = usePermission(permission);
  return allowed ? <>{children}</> : <>{fallback}</>;
}

// ---------------------------------------------------------------------------
// <CanDoAny permissions={["case:edit:any", "case:edit:assigned"]}> — multi-permission gate
// ---------------------------------------------------------------------------

interface CanDoAnyProps {
  permissions: Permission[];
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * Renders children if the user has ANY of the given permissions.
 *
 * Usage:
 *   <CanDoAny permissions={["case:edit:any", "case:edit:assigned"]}>
 *     <button>Edit Case</button>
 *   </CanDoAny>
 */
export function CanDoAny({
  permissions,
  children,
  fallback = null,
}: CanDoAnyProps) {
  const allowed = useAnyPermission(permissions);
  return allowed ? <>{children}</> : <>{fallback}</>;
}
