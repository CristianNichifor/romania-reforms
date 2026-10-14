/**
 * The error state (design screen 03, criterion 7): what failed, and a way to try again.
 *
 * Retrying reloads the page: the data arrives through a dozen independent fetches, and the
 * honest retry is the one that runs all of them again rather than guessing which one broke.
 */
export default function LoadError({
  message,
  retryLabel,
  onRetry,
}: {
  message: string;
  retryLabel: string;
  onRetry: () => void;
}) {
  return (
    <div className="load-error" role="alert">
      <p className="loading">{message}</p>
      <button type="button" className="civic-button load-error-retry" onClick={onRetry}>
        {retryLabel}
      </button>
    </div>
  );
}
