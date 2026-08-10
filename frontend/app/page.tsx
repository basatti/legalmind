"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  // Someone already signed in has no use for a sign-in prompt. Wait for the
  // session check to finish first, or a page refresh bounces them to the
  // signed-out copy for a frame before the user resolves.
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace("/cases");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading || isAuthenticated) {
    return null;
  }

  return (
    <div className="text-center">
      <h1 className="text-2xl font-semibold text-foreground tracking-tight">
        LegalMind
      </h1>
      <p className="text-sm text-subtle mt-2">
        Sign in to manage your cases.
      </p>
    </div>
  );
}
