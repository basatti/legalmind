interface LoadingProps {
  message?: string;
}

export function Loading({ message = "Loading…" }: LoadingProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <div className="w-6 h-6 border-2 border-neutral-300 border-t-neutral-800 rounded-full animate-spin" />
      <p className="text-sm text-neutral-500">{message}</p>
    </div>
  );
}
