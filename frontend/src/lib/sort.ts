import { useState } from "react";

export type SortDirection = "asc" | "desc";

function compareValues(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return -1;
  if (b == null) return 1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

/** Click a sortable <Th> to sort by that column; click it again to flip
 * direction. Used identically across Vendors/Findings/Questionnaires --
 * three real call sites, not a hypothetical one, so a shared hook beats
 * copy-pasting the same six lines into each page. */
export function useSort<T>() {
  const [key, setKey] = useState<keyof T | null>(null);
  const [direction, setDirection] = useState<SortDirection>("asc");

  function toggle(nextKey: keyof T) {
    if (key === nextKey) {
      setDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setKey(nextKey);
      setDirection("asc");
    }
  }

  function directionFor(k: keyof T): SortDirection | null {
    return key === k ? direction : null;
  }

  function apply(rows: T[]): T[] {
    if (!key) return rows;
    const sorted = [...rows].sort((a, b) => compareValues(a[key], b[key]));
    return direction === "asc" ? sorted : sorted.reverse();
  }

  return { toggle, directionFor, apply };
}
