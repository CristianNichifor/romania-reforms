// The error state of the app (UX-12): what failed, in the reader's language, and a way to
// try again. The loaders live in App's effects, so trying again is reloading the page; the
// scenario is in the hash and survives it.
export default function LoadError({ message, retry }: { message: string; retry: string }) {
  return (
    <p className="loading load-error" role="alert">
      <span>{message}</span>{' '}
      <button type="button" className="retry" onClick={() => window.location.reload()}>
        {retry}
      </button>
    </p>
  );
}
