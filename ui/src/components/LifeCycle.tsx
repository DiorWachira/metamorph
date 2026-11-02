import { useEffect, useRef, useState } from "react";

import { creature, STAGES, stageOf } from "../life";

const SEGMENTS = 11;
const SPACING = 7.4;
const CHRYSALIS_FROM_END = 110; // px: out in the margin, so the shell never hangs over text
const CRAWL_FROM = 0.06;

/** The twig is not quite straight, and the creature has to follow it. */
const twigY = (x: number) => 3 * Math.sin(x / 97) + 1.6 * Math.sin(x / 31);

function twigPath(width: number) {
  let d = `M0 ${twigY(0).toFixed(1)}`;
  for (let x = 12; x <= width + 12; x += 12) d += `L${x} ${twigY(x).toFixed(1)}`;
  return d;
}

function leafPath(x: number, y: number, length: number, angle: number) {
  const tip = [x + Math.cos(angle) * length, y + Math.sin(angle) * length];
  const nx = -Math.sin(angle) * length * 0.32;
  const ny = Math.cos(angle) * length * 0.32;
  const mx = x + Math.cos(angle) * length * 0.45;
  const my = y + Math.sin(angle) * length * 0.45;
  return (
    `M${x} ${y}Q${mx + nx} ${my + ny} ${tip[0]} ${tip[1]}Q${mx - nx} ${my - ny} ${x} ${y}Z` +
    `M${x} ${y}L${tip[0]} ${tip[1]}`
  );
}

/** Small leaves along the twig, spaced unevenly but the same on every render at a given width. */
function twigLeaves(width: number) {
  const leaves: string[] = [];
  let x = 34;
  let i = 0;
  while (x < width) {
    const below = i % 3 !== 2;
    const length = 11 + ((i * 37) % 13);
    const angle = below ? 0.5 + ((i * 53) % 60) / 100 : -0.7;
    leaves.push(leafPath(x, twigY(x), length, angle));
    x += 46 + ((i * 71) % 84);
    i += 1;
  }
  return leaves.join("");
}

/**
 * The header's rule is a living twig, and the page's scroll position is a caterpillar on it. It
 * inches along only while you scroll, spins a chrysalis near the far end of the twig, and at the end
 * of the page (or on the later pages of the cabinet) the shell is empty: see <Butterfly />.
 */
export function LifeCycle({ life, onChrysalis }: { life: number; onChrysalis: (x: number, y: number) => void }) {
  const svg = useRef<SVGSVGElement>(null);
  const body = useRef<SVGGElement>(null);
  const [width, setWidth] = useState(1200);
  const now = creature(life);
  const chrysalisX = Math.max(0, width - CHRYSALIS_FROM_END);
  const chrysalisY = twigY(chrysalisX);
  const eggsX = width * CRAWL_FROM + 26;

  useEffect(() => {
    const el = svg.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth || 1200);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const box = svg.current?.getBoundingClientRect();
    if (box) onChrysalis(box.left + chrysalisX, box.top + chrysalisY + 30);
  }, [chrysalisX, chrysalisY, onChrysalis]);

  useEffect(() => {
    // The body is positioned directly: this runs on every scroll frame.
    const group = body.current;
    if (!group) return;
    const start = width * CRAWL_FROM;
    let x = start + (chrysalisX - start) * now.crawl;
    [...group.children].forEach((segment, i) => {
      // A wave of lifted segments runs from tail to head: the looping gait of a real caterpillar.
      const lift = Math.max(0, Math.sin(now.gait - i * 0.8));
      const r = (i === 0 ? 4.8 : 5.4 - Math.abs(i - 5) * 0.14) * now.larvaSize;
      const y = twigY(x) - r - lift * 4.2 * now.larvaSize;
      segment.setAttribute(
        "transform",
        `translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${now.larvaSize.toFixed(3)})`,
      );
      x -= SPACING * now.larvaSize * (1 - lift * 0.22);
    });
  }, [width, chrysalisX, now.crawl, now.gait, now.larvaSize]);

  const shell = "M0 6C7 8 10.5 15 10 22C9.5 30 4 38 0 41C-4 38 -9.5 30 -10 22C-10.5 15 -7 8 0 6Z";

  return (
    <svg ref={svg} className="twig" width="100%" height="72" aria-hidden="true">
      <g transform="translate(0 8)">
        <path className="twig-leaves" d={twigLeaves(width)} />
        <path className="twig-stem" d={twigPath(width)} />

        <g className="eggs" style={{ opacity: now.eggOpacity }} transform={`translate(${eggsX} ${twigY(eggsX)})`}>
          <ellipse cx="0" cy="-3.4" rx="2.5" ry="3.2" />
          <ellipse cx="5.8" cy="-3.2" rx="2.5" ry="3.2" />
          <ellipse cx="-5.6" cy="-3" rx="2.5" ry="3.2" />
        </g>

        <g
          className="chrysalis"
          data-emptied={now.emptied || undefined}
          transform={`translate(${chrysalisX} ${chrysalisY}) scale(${Math.max(now.chrysalisSize, 0.001)})`}
        >
          <path className="silk" d="M0 0V7" />
          <path className="shell" d={shell} />
          <path className="ripe" style={{ opacity: now.emptied ? 0 : now.ripeness }} d={shell} />
          <path className="hatch" d="M-7 15Q0 19 7 15M-8.6 21Q0 25 8.6 21M-7.6 27Q0 31 7.6 27M-5 33Q0 36 5 33M0 8V40" />
          <circle className="gilt" cx="-5" cy="13" r="0.9" />
          <circle className="gilt" cx="5" cy="13" r="0.9" />
          <circle className="gilt" cx="0" cy="11" r="0.9" />
          {now.emptied && <path className="split" d="M0 41L2.5 30L-1.5 24L1.5 17L0 10" />}
        </g>

        <g ref={body} className="larva" style={{ opacity: now.larvaOpacity }}>
          {Array.from({ length: SEGMENTS }, (_, i) => (
            <g key={i} className={i === 0 ? "seg seg-head" : "seg"}>
              <circle r={i === 0 ? 4.8 : 5.4 - Math.abs(i - 5) * 0.14} />
              {i === 0 ? (
                <path className="horns" d="M1 -4L3 -9M-1.5 -4.4L-2.5 -9" />
              ) : (
                <>
                  <path className="spine" d="M0 -5L-1 -9.4M-3 -4L-5 -7.4" />
                  <path className="stripe" d="M-3.6 1.4Q0 3.2 3.6 1.4" />
                  <path className="leg" d="M-1 5V7.4M1.6 5V7.2" />
                </>
              )}
            </g>
          ))}
        </g>
      </g>
    </svg>
  );
}

/** The four stages, printed in the header, with the current one inked in. */
export function LifeScale({ life }: { life: number }) {
  const current = stageOf(life);
  return (
    <ol className="life-scale" aria-hidden="true">
      {STAGES.map((stage) => (
        <li key={stage} data-now={stage === current || undefined}>
          {stage}
        </li>
      ))}
    </ol>
  );
}
