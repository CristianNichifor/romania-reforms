/**
 * Outward links, kept apart from the panel that renders them.
 *
 * One function, because the interesting part is not building the string but deciding when
 * there is no string to build: a payload predating the `uatCode` field, or a UAT the source
 * has no entity for, must produce plain text rather than a link to nowhere.
 */

/** Transparenta.eu's own page for a town hall, keyed on the entity id they publish. */
const TRANSPARENTA_ENTITY_BASE = 'https://www.transparenta.eu/entities/';

/**
 * The budget page for one UAT, or null when the payload cannot say.
 *
 * `code` is transparenta's `uat_code` — the same field the pipeline's GraphQL query already
 * requests. Municipiul Sibiu carries 4270740, and their page is `/entities/4270740`.
 */
export function budgetUrlFor(code: string | undefined | null): string | null {
  if (typeof code !== 'string') return null;
  const trimmed = code.trim();
  if (trimmed === '') return null;
  // Ids are numeric. Anything else is a payload disagreeing with its own schema, and
  // interpolating it into a URL would be how that becomes an injected attribute.
  if (!/^\d+$/.test(trimmed)) return null;
  return `${TRANSPARENTA_ENTITY_BASE}${trimmed}`;
}
