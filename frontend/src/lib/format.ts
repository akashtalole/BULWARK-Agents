/** Formats an ISO timestamp (e.g. "2026-08-29T13:01:40.147149+00:00")
 * for display -- every backend record stamps `created_at`/`last_assessed_at`/etc.
 * with full microsecond precision, which reads as noise in a table cell.
 * Falls back to the raw string for anything that doesn't parse, so a
 * malformed value is still visible rather than silently hidden. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
