import { describe, expect, it } from "vitest";
import { hasAnyPermission, hasPermission, type Permission } from "@/lib/permissions";
import type { Role } from "@/types/api";

/**
 * The permission matrix, tested in both directions.
 *
 * This file is a hand-written mirror of `foundation/permissions.py`. Nothing
 * enforces that the two agree — the backend is the real gate, and this only
 * decides what the UI offers — but a mirror that drifts shows people buttons
 * that 403, or hides ones they are entitled to. These cases pin the rows that
 * are easy to get wrong, and every one asserts a denial as well as a grant: a
 * matrix test that only checks grants passes just as happily against a matrix
 * that grants everything.
 */

const ROLES: Role[] = ["admin", "partner", "attorney", "paralegal"];

describe("hasPermission", () => {
  it("gives only admin user management", () => {
    expect(hasPermission("admin", "user:manage")).toBe(true);
    for (const role of ROLES.filter((r) => r !== "admin")) {
      expect(hasPermission(role, "user:manage")).toBe(false);
    }
  });

  it("gives assignment to partner and admin only", () => {
    expect(hasPermission("partner", "case:assign")).toBe(true);
    expect(hasPermission("admin", "case:assign")).toBe(true);
    expect(hasPermission("attorney", "case:assign")).toBe(false);
    expect(hasPermission("paralegal", "case:assign")).toBe(false);
  });

  it("lets partner read any case, but attorney and paralegal only assigned ones", () => {
    expect(hasPermission("partner", "case:read:any")).toBe(true);
    expect(hasPermission("attorney", "case:read:any")).toBe(false);
    expect(hasPermission("paralegal", "case:read:any")).toBe(false);

    expect(hasPermission("attorney", "case:read:assigned")).toBe(true);
    expect(hasPermission("paralegal", "case:read:assigned")).toBe(true);
  });

  it("gives submit-for-review to attorney and admin, but not partner", () => {
    // The backend comments this permission "# Attorney-only", which is true
    // only among the working roles: admin is a deliberate superset of every
    // other role (see the matrix docstring in foundation/permissions.py), so
    // it holds this too. Asserting the comment instead of the data is exactly
    // the mistake this test caught when it was first written.
    //
    // Partner is the meaningful denial: the person who reviews the work is not
    // the person who submits it for review.
    expect(hasPermission("attorney", "case:submit_for_review")).toBe(true);
    expect(hasPermission("admin", "case:submit_for_review")).toBe(true);
    expect(hasPermission("partner", "case:submit_for_review")).toBe(false);
    expect(hasPermission("paralegal", "case:submit_for_review")).toBe(false);
  });

  it("gives review and close to partner and admin, never to the people doing the work", () => {
    for (const permission of ["case:review", "case:close"] as Permission[]) {
      expect(hasPermission("partner", permission)).toBe(true);
      expect(hasPermission("admin", permission)).toBe(true);
      expect(hasPermission("attorney", permission)).toBe(false);
      expect(hasPermission("paralegal", permission)).toBe(false);
    }
  });

  it("gives deletion to admin alone", () => {
    expect(hasPermission("admin", "case:delete")).toBe(true);
    for (const role of ROLES.filter((r) => r !== "admin")) {
      expect(hasPermission(role, "case:delete")).toBe(false);
    }
  });

  it("does not let a paralegal create a case", () => {
    expect(hasPermission("paralegal", "case:create")).toBe(false);
    expect(hasPermission("paralegal", "case:edit:assigned")).toBe(true);
  });
});

describe("hasAnyPermission", () => {
  it("is true when the role holds either one", () => {
    // The real call site: the sidebar shows Cases to anyone who can read one.
    expect(hasAnyPermission("paralegal", ["case:read:any", "case:read:assigned"])).toBe(true);
  });

  it("is false when the role holds neither", () => {
    expect(hasAnyPermission("paralegal", ["user:manage", "case:delete"])).toBe(false);
  });

  it("is false for an empty list rather than vacuously true", () => {
    // `some` on an empty array is false, which is the safe direction — an
    // empty requirement must not grant access.
    expect(hasAnyPermission("admin", [])).toBe(false);
  });
});
