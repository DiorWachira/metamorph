/**
 * The life cycle of the page. `life` runs from 0 (an egg) to 1 (a butterfly on the wing). On every
 * page it starts from that page's place in the cycle and scrolling carries it onward, so a page too
 * short to scroll still shows its own stage.
 */

export type Stage = "ovum" | "larva" | "pupa" | "imago";

export const STAGES: readonly Stage[] = ["ovum", "larva", "pupa", "imago"];

const HATCH = 0.06; // the egg opens
const PUPATE = 0.62; // the caterpillar stops and spins
const SEALED = 0.72; // the chrysalis is complete
const ECLOSE = 0.82; // the butterfly leaves it

const clamp = (value: number, low = 0, high = 1) => Math.min(high, Math.max(low, value));
const ramp = (value: number, from: number, to: number) => clamp((value - from) / (to - from));

/** Where each page sits in the cycle: the further into a run's review, the older the creature. */
export function baseLife(pathname: string): number {
  if (pathname === "/") return 0;
  if (pathname === "/runs") return 0.22;
  if (pathname.startsWith("/runs/")) return 0.34;
  if (pathname.startsWith("/cases/")) return 0.48;
  if (pathname === "/relations") return 0.74;
  if (pathname === "/lab") return 0.86;
  return 0; // an unknown page: an egg nobody has catalogued yet
}

export function lifeAt(base: number, scrollProgress: number): number {
  return clamp(base + (1 - base) * clamp(scrollProgress));
}

export function stageOf(life: number): Stage {
  if (life < HATCH) return "ovum";
  if (life < PUPATE) return "larva";
  if (life < ECLOSE) return "pupa";
  return "imago";
}

/** Everything the drawing needs at one moment of the cycle. */
export function creature(life: number) {
  return {
    /** How far along the twig the caterpillar has crawled, 0 to 1. */
    crawl: ramp(life, HATCH, PUPATE),
    /** The caterpillar grows through its instars, then is gone inside the chrysalis. */
    larvaSize: life < HATCH ? 0 : 0.55 + 0.45 * ramp(life, HATCH, PUPATE),
    larvaOpacity: life < HATCH ? 0 : 1 - ramp(life, PUPATE, PUPATE + 0.05),
    eggOpacity: 1 - ramp(life, HATCH - 0.01, HATCH + 0.04) * 0.65,
    chrysalisSize: ramp(life, PUPATE, SEALED),
    /** A Morpho's blue shows through the shell just before it opens. */
    ripeness: ramp(life, SEALED, ECLOSE),
    emptied: life >= ECLOSE,
    butterfly: life >= ECLOSE,
    /** Advances only with `life`, so the body inches while scrolling and rests when you rest. */
    gait: life * 340,
  };
}
