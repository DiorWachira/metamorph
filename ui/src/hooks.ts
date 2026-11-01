import { useCallback, useEffect, useState } from "react";

export type Loadable<T> =
  | { state: "loading" }
  | { state: "error"; error: Error }
  | { state: "ready"; data: T };

/** Load data for a page; re-runs when `deps` change. `reload` refetches in place. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]): [Loadable<T>, () => void] {
  const [value, setValue] = useState<Loadable<T>>({ state: "loading" });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    setValue((v) => (v.state === "ready" && tick > 0 ? v : { state: "loading" }));
    load().then(
      (data) => live && setValue({ state: "ready", data }),
      (error: Error) => live && setValue({ state: "error", error }),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return [value, useCallback(() => setTick((t) => t + 1), [])];
}

/** Read/write a per-viewer preference; storage can be unavailable, so every access is guarded. */
export function useStored<T extends string>(key: string, fallback: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      return (localStorage.getItem(key) as T | null) ?? fallback;
    } catch {
      return fallback;
    }
  });
  const set = useCallback(
    (next: T) => {
      setValue(next);
      try {
        localStorage.setItem(key, next);
      } catch {
        /* private mode or blocked storage: keep it in memory only */
      }
    },
    [key],
  );
  return [value, set];
}
