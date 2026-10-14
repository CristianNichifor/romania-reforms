// Simulator paths renamed by the English addresses (#147), old name to new. The old addresses
// are linked from outside the repository, so they redirect rather than 404. The object is
// written as JSON because scripts/redirect_stubs.py reads it too: one list for both.
export const BASE = "/romania-reforms/";

export const RENAMED_PATHS = Object.freeze({
  "administrativ": "administrative-reform",
  "salarizare": "public-pay"
});

// The new address for an old path, or null. Relative, so the hub's host is kept; the browser
// carries the #hash over a redirect whose Location has none.
export function renamedLocation(url) {
  const { pathname, search } = new URL(url);
  if (!pathname.startsWith(BASE)) return null;
  const rest = pathname.slice(BASE.length);
  const slash = rest.indexOf("/");
  const head = slash === -1 ? rest : rest.slice(0, slash);
  const target = Object.hasOwn(RENAMED_PATHS, head) ? RENAMED_PATHS[head] : null;
  if (target === null) return null;
  const tail = slash === -1 ? "/" : rest.slice(slash);
  return `${BASE}${target}${tail}${search}`;
}
