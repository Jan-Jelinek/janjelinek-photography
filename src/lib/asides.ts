/** A text section or aside: one string, or a list of text and image file names. */
export type TextItems = string | string[];

/**
 * For an aside row (`aside: …` or `aside-3: …`): its items and the photo it's about (1-based, in
 * reading order; undefined = the row's top-right photo). Anything else: undefined.
 */
export function asideOf(row: unknown): { target?: number; items: TextItems } | undefined {
  if (!row || typeof row !== "object" || Array.isArray(row)) return undefined;
  const [key, items] = Object.entries(row)[0] ?? [];
  const m = key?.match(/^aside(?:-([1-9]\d*))?$/);
  return m ? { target: m[1] ? Number(m[1]) : undefined, items: items as TextItems } : undefined;
}
