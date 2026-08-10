interface LoadingProps {
  message?: string;
}

export function Loading({ message = "Loading…" }: LoadingProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <div className="w-6 h-6 border-2 border-border-strong border-t-foreground rounded-full animate-spin" />
      <p className="text-sm text-subtle">{message}</p>
    </div>
  );
}
