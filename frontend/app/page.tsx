import { RequireAuth } from "@/components/RequireAuth";

export default function Home() {
  return (
    <RequireAuth>
      <div className="text-center">
        <h1 className="text-2xl font-semibold text-neutral-900 tracking-tight">
          LegalMind
        </h1>
        <p className="text-sm text-neutral-500 mt-2">
          Sign in to manage your cases.
        </p>
      </div>
    </RequireAuth>
  );
}
