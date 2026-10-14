import { useEffect, useState } from 'react';

/** After this long the loader stops saying "loading" and says "computing" (screen 03, criterion 7). */
export const LOADER_STAGE_MS = 2000;

/** Which of the two loader texts applies after `elapsedMs`. */
export function loaderText(elapsedMs: number, first: string, later: string): string {
  return elapsedMs >= LOADER_STAGE_MS ? later : first;
}

/**
 * The loading state: visible at once, and honest about a slow load. A reader who has waited two
 * seconds is told the page is still working rather than left with the same first line.
 */
export default function Loader({ first, later }: { first: string; later: string }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const timer = setTimeout(() => setElapsed(LOADER_STAGE_MS), LOADER_STAGE_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    <p className="loading" role="status" aria-live="polite">
      {loaderText(elapsed, first, later)}
    </p>
  );
}
