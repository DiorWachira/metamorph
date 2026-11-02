import { useEffect, useMemo, useRef } from "react";

import { asset } from "../format";
import { prefersReducedMotion } from "./Alive";

/** Seeded so that the same specks of pollen drift across the page on every visit. */
function scatter(count: number) {
  let state = 41;
  const next = () => {
    state = (state * 16807) % 2147483647;
    return state / 2147483647;
  };
  return Array.from({ length: count }, () => ({
    left: `${(next() * 100).toFixed(1)}%`,
    top: `${(next() * 100).toFixed(1)}%`,
    animationDelay: `${(-next() * 24).toFixed(1)}s`,
    animationDuration: `${(14 + next() * 16).toFixed(1)}s`,
  }));
}

/**
 * The host plant. Merian never drew an insect without the plant it feeds on, so the whole site
 * stands in one: two blocks of printed foliage, specimens cut from her plates, and a sky that turns
 * from dawn to dusk over the length of the page. Decorative, fixed behind everything.
 */
export function Habitat({ life, home }: { life: number; home: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  const pollen = useMemo(() => scatter(16), []);

  useEffect(() => {
    root.current?.style.setProperty("--life", String(life));
  }, [life]);

  useEffect(() => {
    const el = root.current;
    if (!el || prefersReducedMotion()) return;
    const tiles = [...el.querySelectorAll<HTMLElement>("[data-tile]")];
    const drifters = [...el.querySelectorAll<HTMLElement>("[data-drift]")];
    let frame = 0;
    const paint = () => {
      frame = 0;
      const y = window.scrollY;
      const span = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      for (const tile of tiles) {
        // Wrap at the tile's size, so the layer never runs out however long the page is.
        const moved = (y * Number(tile.dataset.depth)) % Number(tile.dataset.tile);
        tile.style.transform = `translate3d(0, ${-moved}px, 0)`;
      }
      for (const drifter of drifters) {
        drifter.style.transform = `translate3d(0, ${(-y / span) * Number(drifter.dataset.drift)}px, 0)`;
      }
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(paint);
    };
    paint();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <div ref={root} className="habitat" data-home={home || undefined} aria-hidden="true">
      <div className="sky sky-dawn" />
      <div className="sky sky-dusk" />
      <div className="tile tile-back" data-tile="900" data-depth="0.06" />
      <div className="tile tile-front" data-tile="620" data-depth="0.14" />
      <img className="specimen sp-frangipani" data-drift="150" src={asset("habitat/frangipani.webp")} alt="" />
      <img className="specimen sp-branch" data-drift="240" src={asset("habitat/branch.webp")} alt="" />
      <img className="specimen sp-moth" data-drift="520" src={asset("habitat/moth.webp")} alt="" />
      <img className="specimen sp-morpho" data-drift="380" src={asset("habitat/morpho.webp")} alt="" />
      <div className="calm">
        <div className="sky sky-dawn" />
        <div className="sky sky-dusk" />
      </div>
      <div className="grain" />
      <div className="pollen">
        {pollen.map((style, i) => (
          <i key={i} style={style} />
        ))}
      </div>
    </div>
  );
}
