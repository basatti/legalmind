"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api-client";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Incorrect email or password.");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen w-full flex">
      {/* Left panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-ink text-paper flex-col justify-between p-12">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full border border-brass-light flex items-center justify-center font-serif text-sm">
            L
          </div>
          <span className="font-serif text-lg tracking-wide">LegalMind</span>
        </div>

        <div>
          <p className="text-xs tracking-[0.2em] text-brass-light uppercase mb-4">
            Case management, ordered
          </p>
          <h1 className="font-serif text-5xl leading-tight mb-4">
            Every case,<br />on the record.
          </h1>
          <p className="text-sm text-paper/60 max-w-sm">
            One file, one docket, one source of truth — from intake to closing argument.
          </p>
        </div>

        <p className="text-xs tracking-[0.15em] text-paper/40 uppercase">
          Docket System · Est. 2026
        </p>
      </div>

      {/* Right panel */}
      <div className="w-full lg:w-1/2 bg-paper flex flex-col justify-center items-center px-6">
        <form onSubmit={handleSubmit} className="w-full max-w-sm flex flex-col gap-6">
          <div>
            <h2 className="font-serif text-3xl text-ink">Sign in</h2>
            <p className="text-sm text-slate mt-1">
              Enter your credentials to access your docket.
            </p>
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="email" className="text-xs tracking-wide uppercase text-slate">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="bg-transparent border-0 border-b border-ink/20 px-0 py-2 text-sm text-ink focus:outline-none focus:border-brass transition-colors"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="password" className="text-xs tracking-wide uppercase text-slate">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="bg-transparent border-0 border-b border-ink/20 px-0 py-2 text-sm text-ink focus:outline-none focus:border-brass transition-colors"
            />
          </div>

          {error && <p className="text-sm text-oxblood">{error}</p>}

          <button
            type="submit"
            disabled={isSubmitting}
            className="bg-ink text-paper text-sm font-medium rounded-md py-3 hover:bg-ink-2 transition-colors disabled:opacity-50"
          >
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>

          <p className="text-xs text-center text-slate">
            Access is provisioned by your administrator.
          </p>
        </form>
      </div>
    </div>
  );
}
