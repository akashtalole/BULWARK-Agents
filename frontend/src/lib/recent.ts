import { useCallback, useEffect, useState } from "react";

/** BULWARK's API has no list endpoints for questionnaires (by design --
 * see api/routes.py) so this dashboard remembers submitted ids locally,
 * per browser, to make "go look at what I just submitted" usable without
 * inventing an endpoint the backend doesn't have. */
export function useRecentIds(key: string, max = 20) {
  const storageKey = `bulwark.recent.${key}`;
  const [ids, setIds] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(storageKey) ?? "[]");
    } catch {
      return [];
    }
  });

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(ids));
  }, [ids, storageKey]);

  const add = useCallback(
    (id: string) => {
      setIds((prev) => [id, ...prev.filter((x) => x !== id)].slice(0, max));
    },
    [max],
  );

  const clear = useCallback(() => setIds([]), []);

  return { ids, add, clear };
}
