import Link from "next/link";

export default function Home() {
  return (
    <div className="text-center">
      <h1 className="text-2xl font-semibold text-neutral-900 tracking-tight">
        LegalMind
      </h1>
      <p className="text-sm text-neutral-500 mt-2">
        Sign in to manage your cases.
      </p>
      <Link
        href="/login"
        className="inline-block mt-4 text-sm text-neutral-900 underline"
      >
        Go to sign in
      </Link>
    </div>
  );
}
