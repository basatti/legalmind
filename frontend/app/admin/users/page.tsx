"use client";

import { useEffect, useState, type FormEvent } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { CanDo } from "@/components/CanDo";
import { NotAuthorized, SectionLabel } from "@/components/ui";
import { apiClient, ApiError } from "@/lib/api-client";
import type { Role, User } from "@/types/api";

export default function AdminUsersPage() {
  return (
    <RequireAuth>
      <CanDo
        permission="user:manage"
        fallback={<NotAuthorized message="Only admins can manage users." />}
      >
        <UserManagement />
      </CanDo>
    </RequireAuth>
  );
}

function UserManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(true);

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [role, setRole] = useState<Role>("attorney");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  
  async function loadUsers() {
    setIsLoadingUsers(true);
    try {
      const data = await apiClient.users.list();
      setUsers(data);
    } finally {
      setIsLoadingUsers(false);
    }
  }
useEffect(() => {
  async function fetch() {
    await loadUsers();
  }
  void fetch();
}, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const newUser = await apiClient.users.create({
        email,
        full_name: fullName,
        temporary_password: temporaryPassword,
        role,
      });
      setUsers((prev) => [...prev, newUser]);
      setEmail("");
      setFullName("");
      setTemporaryPassword("");
      setRole("attorney");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("A user with this email already exists.");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-xl font-semibold text-foreground">User Management</h1>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-4 bg-surface border border-border rounded-xl shadow-sm p-6 max-w-xl"
      >
        <SectionLabel>Create User</SectionLabel>

        <div className="flex flex-col gap-1">
          <label htmlFor="email" className="text-sm text-muted">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-foreground focus:border-transparent"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="full_name" className="text-sm text-muted">
            Full Name
          </label>
          <input
            id="full_name"
            type="text"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-foreground focus:border-transparent"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="temporary_password" className="text-sm text-muted">
            Temporary Password
          </label>
          <input
            id="temporary_password"
            type="text"
            required
            value={temporaryPassword}
            onChange={(e) => setTemporaryPassword(e.target.value)}
            className="border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-foreground focus:border-transparent"
          />
          <p className="text-xs text-faint">
            The user must change this on first login.
          </p>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="role" className="text-sm text-muted">
            Role
          </label>
          <select
            id="role"
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            className="border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-foreground focus:border-transparent"
          >
            <option value="admin">Admin</option>
            <option value="partner">Partner</option>
            <option value="attorney">Attorney</option>
            <option value="paralegal">Paralegal</option>
          </select>
        </div>

        {error && <p className="text-sm text-danger-fg">{error}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="bg-primary text-primary-foreground text-sm rounded-md py-2 hover:bg-primary-hover transition-colors disabled:opacity-50"
        >
          {isSubmitting ? "Creating…" : "Create User"}
        </button>
      </form>

      <div className="flex flex-col gap-2 max-w-xl">
        <SectionLabel>Existing Users</SectionLabel>
        {isLoadingUsers ? (
          <p className="text-sm text-subtle">Loading…</p>
        ) : (
          <div className="bg-surface border border-border rounded-xl shadow-sm divide-y divide-border-subtle">
            {users.map((u) => (
              <div key={u.id} className="flex items-center justify-between px-4 py-3">
                <div>
                  <p className="text-sm text-foreground">{u.full_name}</p>
                  <p className="text-xs text-subtle">{u.email}</p>
                </div>
                <span className="text-xs uppercase tracking-wide text-subtle">
                  {u.role}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
