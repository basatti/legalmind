/**
 * NotAuthorized — shown when the backend rejects an action with 403.
 *
 * Usage:
 *   try {
 *     await apiClient.cases.create(data);
 *   } catch (err) {
 *     if (err instanceof ApiError && err.status === 403) {
 *       // render <NotAuthorized />
 *     }
 *   }
 */

interface NotAuthorizedProps {
  message?: string;
}

export function NotAuthorized({
  message = "You don't have permission to perform this action.",
}: NotAuthorizedProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <div className="w-10 h-10 rounded-full bg-amber-50 flex items-center justify-center">
        <span className="text-amber-500 text-lg font-medium">✕</span>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-neutral-800">Not Authorized</p>
        <p className="text-sm text-neutral-500 mt-1">{message}</p>
      </div>
    </div>
  );
}
