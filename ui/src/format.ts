import type { CaseView, Status } from "./api";

export const catalogueNo = (id: number) => `MM·${String(id).padStart(4, "0")}`;

export const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined ? "n/a" : `${(x * 100).toFixed(digits)}%`;

export const score = (x: number | null | undefined) =>
  x === null || x === undefined ? "n/a" : x.toFixed(2);

export const usd = (x: number) => (x === 0 ? "$0" : x < 0.01 ? `$${x.toFixed(4)}` : `$${x.toFixed(2)}`);

export const shortSha = (sha: string | null) => (sha ? sha.slice(0, 10) : "no commit");

export function when(iso: string): string {
  const date = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** The visual class of a case: "excused" is a pass that only the baseline saved. */
export function caseClass(c: Pick<CaseView, "status" | "excused_by_baseline">): string {
  return c.excused_by_baseline ? "st-excused" : `st-${c.status}`;
}

export const STATUS_WORD: Record<Status, string> = {
  pass: "intact",
  violation: "mutation",
  inconclusive: "inconclusive",
  error: "error",
  skipped: "skipped",
};

export const TRIAGE_WORD = {
  unreviewed: "undetermined",
  true_bug: "true defect",
  false_alarm: "false alarm",
} as const;

/** Readable text for an input value (strings as-is, structures as JSON). */
export function show(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/** A file from ui/public, wherever the UI is hosted. */
export const asset = (path: string) => `${import.meta.env.BASE_URL}${path}`;
