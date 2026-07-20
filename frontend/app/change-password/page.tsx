"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { RequireAuth } from "@/components/RequireAuth";
import { useAuth } from "@/lib/auth";
import { apiClient, ApiError } from "@/lib/api-client";

export default function ChangePasswordPage() {
  return (
    <RequireAuth>
      <ChangePasswordForm />
    </RequireAuth>
  );
}

function ChangePasswordForm() {
  const { refreshUser } = useAuth();
  const router = useRouter();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError("New password and confirmation don't match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await apiClient.auth.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      await refreshUser();
      router.push("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Current password is incorrect.");
      } else if (err instanceof ApiError && err.status === 422) {
        setError("Password must be at least 8 characters and include a letter and a number.");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-sm flex flex-col gap-4 bg-white border border-neutral-200 rounded-xl shadow-sm p-8"
    >
      <div>
        <h1 className="text-lg font-semibold text-neutral-900">Set a new password</h1>
        <p className="text-sm text-neutral-500 mt-1">
          You&apos;re using a temporary password. Set a permanent one to continue.
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="current-password" className="text-sm text-neutral-600">
          Current (temporary) password
        </label>
        <input
          id="current-password"
          type="password"
          required
          autoFocus
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="new-password" className="text-sm text-neutral-600">
          New password
        </label>
        <input
          id="new-password"
          type="password"
          required
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="confirm-password" className="text-sm text-neutral-600">
          Confirm new password
        </label>
        <input
          id="confirm-password"
          type="password"
          required
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={isSubmitting}
        className="bg-neutral-900 text-white text-sm rounded-md py-2 hover:bg-neutral-800 transition-colors disabled:opacity-50"
      >
        {isSubmitting ? "Saving…" : "Set new password"}
      </button>
    </form>
  );
}
