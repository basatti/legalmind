interface EmptyStateProps {
  title?: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({
  title = "Nothing here yet",
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <div className="w-10 h-10 rounded-full bg-neutral-100 flex items-center justify-center">
        <span className="text-neutral-400 text-lg">○</span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-neutral-800">{title}</p>
        {description && (
          <p className="text-sm text-neutral-500 mt-1">{description}</p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
