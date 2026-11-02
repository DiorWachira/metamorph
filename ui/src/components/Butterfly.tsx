import { useEffect, useRef } from "react";

import { prefersReducedMotion } from "./Alive";

const PERCHES = "a, button, .tray, .reading-step, .figures, .det-slip, .plate, h1, h2";
const IDLE_PERCHES = ".section-head h2, .page-head h1, .hero h1";
const IDLE_AFTER = 4000;

/** Half a Morpho, drawn from the wing root. Mirrored for the other side. */
function Wing({ side }: { side: "left" | "right" }) {
  const outline =
    "M1 21C8 8 22 1 38 1C43 1 46 3 45 7C44 13 41 18 38 22C39 26 37 29 34 31C35 37 32 42 28 46C24 51 17 53 12 50C6 47 2 39 1 30Z";
  const inner =
    "M3 22C9 12 21 6 34 6C39 6 41 8 40 11C39 15 36 19 33 22C34 26 32 28 29 30C30 35 27 39 24 42C21 46 16 47 12 45C8 43 4 36 3 29Z";
  const id = `morpho-${side}`;
  return (
    <span className={`wing wing-${side}`}>
      <svg viewBox="0 0 48 54" width="100%" height="100%">
        <defs>
          <linearGradient id={id} x1="0" y1="0.6" x2="1" y2="0.2">
            <stop offset="0" stopColor="#123a78" />
            <stop offset="0.55" stopColor="#1f7fd0" />
            <stop offset="1" stopColor="#5cc4f0" />
          </linearGradient>
        </defs>
        <path d={outline} fill="#15161b" />
        <path d={inner} fill={`url(#${id})`} />
        {/* Structural colour: at a low angle the same wing reads violet-brown (see setWings). */}
        <path className="wing-sheen" d={inner} fill="#3a1f5c" />
        <path
          d="M2 22L38 8M2 23L36 15M2 24L32 22M2 26L28 31M3 28L24 38M4 30L17 44"
          fill="none"
          stroke="#0b1020"
          strokeWidth="0.55"
          opacity="0.55"
        />
        <g fill="#efe9da">
          <circle cx="40" cy="6.5" r="1" />
          <circle cx="37" cy="13" r="0.9" />
          <circle cx="33" cy="19" r="0.8" />
          <circle cx="29" cy="40" r="0.9" />
          <circle cx="22" cy="47" r="1" />
          <circle cx="14" cy="48" r="0.8" />
        </g>
      </svg>
    </span>
  );
}

/**
 * The imago. Once it has left the chrysalis it follows the mouse at a butterfly's own unreliable
 * pace, and settles on whatever you are looking at, closing its wings to rest. Left alone (or on a
 * touch screen) it finds a heading to sit on. With reduced motion it simply rests by the empty shell.
 */
export function Butterfly({ free, from }: { free: boolean; from: { x: number; y: number } }) {
  const el = useRef<HTMLDivElement>(null);
  const start = useRef(from);
  start.current = from;

  useEffect(() => {
    const node = el.current;
    if (!node || !free) return;
    const left = node.querySelector<HTMLElement>(".wing-left")!;
    const right = node.querySelector<HTMLElement>(".wing-right")!;
    const sheens = [...node.querySelectorAll<SVGPathElement>(".wing-sheen")];
    const setWings = (angle: number) => {
      left.style.transform = `rotateY(${angle}deg)`;
      right.style.transform = `rotateY(${-angle}deg)`;
      const sheen = (Math.sin((angle * Math.PI) / 180) ** 2 * 0.7).toFixed(2);
      for (const path of sheens) path.style.opacity = sheen;
    };

    if (prefersReducedMotion()) {
      node.style.transform = `translate3d(${start.current.x + 18}px, ${start.current.y + 8}px, 0)`;
      setWings(20);
      return;
    }

    let x = start.current.x;
    let y = start.current.y;
    let targetX = x + 40;
    let targetY = y + 70;
    let perching = false;
    let lastMove = -Infinity;
    let pointerX = 0;
    let pointerY = 0;
    let hovered: Element | null = null;
    let frame = 0;
    let wingPhase = 0;
    let previous = performance.now();
    let nextLook = 0;

    const onPointer = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      lastMove = performance.now();
      pointerX = e.clientX;
      pointerY = e.clientY;
      hovered = e.target instanceof Element ? e.target.closest(PERCHES) : null;
    };

    const look = (now: number) => {
      if (now - lastMove < IDLE_AFTER) {
        const box = hovered?.isConnected ? hovered.getBoundingClientRect() : null;
        if (box && box.bottom > 0 && box.top < window.innerHeight) {
          perching = true;
          targetX = Math.min(box.right - 12, Math.max(box.left + 12, pointerX));
          targetY = Math.max(38, box.top); // its wings stay on screen above the nav
        } else {
          perching = false;
          targetX = pointerX - 34;
          targetY = pointerY - 30;
        }
        return;
      }
      // Alone: settle on the first heading or button in view, below the sticky header.
      perching = true;
      for (const candidate of document.querySelectorAll(IDLE_PERCHES)) {
        const box = candidate.getBoundingClientRect();
        if (box.top > 96 && box.top < window.innerHeight - 60) {
          targetX = box.right; // the end of the heading, clear of its words
          targetY = box.top;
          return;
        }
      }
      perching = false;
      targetX = window.innerWidth * 0.8;
      targetY = window.innerHeight * 0.3;
    };

    const fly = (now: number) => {
      frame = requestAnimationFrame(fly);
      if (document.hidden) return;
      const dt = Math.min(0.05, (now - previous) / 1000);
      previous = now;
      if (now > nextLook) {
        look(now);
        nextLook = now + 160;
      }
      const dx = targetX - x;
      const dy = targetY - y;
      const distance = Math.hypot(dx, dy);
      const settled = perching && distance < 4;
      const flutter = settled ? 0 : Math.min(1, distance / 60) * 26;
      // Butterflies never fly straight: a slow weave on top of the pursuit.
      const weaveX = Math.sin(now / 310) * flutter + Math.sin(now / 127) * flutter * 0.3;
      const weaveY = Math.cos(now / 240) * flutter * 0.8;
      const pull = 1 - Math.exp(-dt * (perching ? 3.4 : 2.1));
      x += dx * pull + weaveX * dt * 3;
      y += dy * pull + weaveY * dt * 3;

      wingPhase += dt * (settled ? 1.5 : 34);
      const angle = settled
        ? 34 + Math.sin(wingPhase) * 16 // resting: wings half open, moving slowly
        : 38 + Math.sin(wingPhase) * 36;
      const tilt = settled ? 0 : Math.max(-28, Math.min(28, dx * 0.16));
      node.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) rotate(${tilt.toFixed(1)}deg)`;
      setWings(angle);
    };

    window.addEventListener("pointermove", onPointer, { passive: true });
    frame = requestAnimationFrame(fly);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onPointer);
    };
  }, [free]);

  return (
    <div ref={el} className="butterfly" data-free={free || undefined} aria-hidden="true">
      <div className="butterfly-body">
        <Wing side="left" />
        <i className="thorax" />
        <Wing side="right" />
      </div>
    </div>
  );
}
