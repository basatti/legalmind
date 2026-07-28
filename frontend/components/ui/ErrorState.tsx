interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({
  message = "Something went wrong.",
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4">
      <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center">
        <span className="text-red-500 text-lg font-medium">!</span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-neutral-800">Error</p>
        <p className="text-sm text-neutral-500 mt-1">{message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-sm text-neutral-600 underline underline-offset-2 hover:text-neutral-900 transition-colors"
        >
          Try again
        </button>
      )}
    </div>
  );
}
