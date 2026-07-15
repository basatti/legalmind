"use client";

import { useEffect, useState, type FormEvent } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { CanDo } from "@/components/CanDo";
import { NotAuthorized } from "@/components/ui";
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
    <div className="max-w-2xl mx-auto py-10 flex flex-col gap-8">
      <h1 className="text-xl font-semibold text-neutral-900">User Management</h1>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-4 bg-white border border-neutral-200 rounded-xl shadow-sm p-6"
      >
        <h2 className="text-sm font-medium text-neutral-800">Create User</h2>

        <div className="flex flex-col gap-1">
          <label htmlFor="email" className="text-sm text-neutral-600">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="full_name" className="text-sm text-neutral-600">
            Full Name
          </label>
          <input
            id="full_name"
            type="text"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="temporary_password" className="text-sm text-neutral-600">
            Temporary Password
          </label>
          <input
            id="temporary_password"
            type="text"
            required
            value={temporaryPassword}
            onChange={(e) => setTemporaryPassword(e.target.value)}
            className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
          />
          <p className="text-xs text-neutral-400">
            The user must change this on first login.
          </p>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="role" className="text-sm text-neutral-600">
            Role
          </label>
          <select
            id="role"
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
          >
            <option value="admin">Admin</option>
            <option value="partner">Partner</option>
            <option value="attorney">Attorney</option>
            <option value="paralegal">Paralegal</option>
          </select>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="bg-neutral-900 text-white text-sm rounded-md py-2 hover:bg-neutral-800 transition-colors disabled:opacity-50"
        >
          {isSubmitting ? "Creating…" : "Create User"}
        </button>
      </form>

      <div className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-neutral-800">Existing Users</h2>
        {isLoadingUsers ? (
          <p className="text-sm text-neutral-500">Loading…</p>
        ) : (
          <div className="bg-white border border-neutral-200 rounded-xl shadow-sm divide-y divide-neutral-100">
            {users.map((u) => (
              <div key={u.id} className="flex items-center justify-between px-4 py-3">
                <div>
                  <p className="text-sm text-neutral-900">{u.full_name}</p>
                  <p className="text-xs text-neutral-500">{u.email}</p>
                </div>
                <span className="text-xs uppercase tracking-wide text-neutral-500">
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
