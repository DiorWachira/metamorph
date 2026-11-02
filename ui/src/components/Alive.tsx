import { useEffect, useRef, useState, type PointerEvent } from "react";

/** How long the page stays hand-coloured after the last movement, scroll or key press. */
export const IDLE_MS = 2600;

export const prefersReducedMotion = () =>
  typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * The cabinet comes alive while it is being used. Any pointer movement, scroll, wheel, touch or
 * key press sets `data-alive` on <html> (CSS lets the pigments seep in), and the cursor position
 * feeds the reading lamp through `--mx`/`--my`. After IDLE_MS of stillness the attribute is
 * removed and the page drains back to ink on paper.
 *
 * With reduced motion the page simply stays coloured: no lamp, nothing that follows the cursor.
 */
export function useAliveCabinet() {
  useEffect(() => {
    const root = document.documentElement;
    if (prefersReducedMotion()) {
      root.dataset.alive = "still";
      return () => {
        delete root.dataset.alive;
      };
    }

    let idleTimer: number | undefined;
    let frame = 0;
    const wake = () => {
      if (root.dataset.alive !== "true") root.dataset.alive = "true";
      window.clearTimeout(idleTimer);
      idleTimer = window.setTimeout(() => delete root.dataset.alive, IDLE_MS);
    };
    const onPointer = (e: globalThis.PointerEvent) => {
      wake();
      if (e.pointerType !== "mouse") return; // the lamp follows a mouse, not a finger
      root.dataset.lamp = "on"; // and stays off until there is a mouse to follow
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        root.style.setProperty("--mx", `${e.clientX}px`);
        root.style.setProperty("--my", `${e.clientY}px`);
      });
    };

    window.addEventListener("pointermove", onPointer, { passive: true });
    window.addEventListener("pointerdown", onPointer, { passive: true });
    window.addEventListener("scroll", wake, { passive: true });
    window.addEventListener("wheel", wake, { passive: true });
    window.addEventListener("keydown", wake);
    return () => {
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("scroll", wake);
      window.removeEventListener("wheel", wake);
      window.removeEventListener("keydown", wake);
      window.clearTimeout(idleTimer);
      cancelAnimationFrame(frame);
      delete root.dataset.alive;
      delete root.dataset.lamp;
    };
  }, []);
}

/** The reading lamp: a soft pool of Morpho blue that follows the mouse while the page is alive. */
export function Lamp() {
  return <div className="lamp" aria-hidden="true" />;
}

/**
 * An engraved plate that the visitor hand-colours. At rest it is ink on paper. Hovering lets the
 * colour bloom outward from the cursor until the whole plate is coloured; going idle drains it.
 * `coloured` keeps it fully coloured (the explicit "hand-colour the plate" choice).
 */
export function ColourPlate({
  src,
  alt,
  width,
  height,
  coloured = false,
  cover = false,
  className = "",
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
  coloured?: boolean;
  cover?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [touched, setTouched] = useState(false);

  const aim = (e: PointerEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const box = el.getBoundingClientRect();
    el.style.setProperty("--px", `${e.clientX - box.left}px`);
    el.style.setProperty("--py", `${e.clientY - box.top}px`);
  };

  return (
    <div
      ref={ref}
      className={`colour-plate ${cover ? "is-cover" : ""} ${coloured || touched ? "is-coloured" : ""} ${className}`}
      onPointerEnter={aim}
      onPointerMove={aim}
      // A tap on a touch screen has no hover: it colours the plate outright.
      onPointerDown={(e) => e.pointerType !== "mouse" && setTouched((t) => !t)}
    >
      <img className="engraving" src={src} width={width} height={height} alt={alt} />
      <img className="pigment" src={src} width={width} height={height} alt="" aria-hidden="true" />
    </div>
  );
}
