import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { READ_ONLY } from "../api";
import { useStored } from "../hooks";
import { baseLife, creature, lifeAt } from "../life";
import { Lamp, useAliveCabinet } from "./Alive";
import { Butterfly } from "./Butterfly";
import { Habitat } from "./Habitat";
import { LifeCycle, LifeScale } from "./LifeCycle";

type Theme = "system" | "light" | "dark";
const NEXT: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };

function ThemeToggle() {
  const [theme, setTheme] = useStored<Theme>("mm-theme", "system");
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
  }, [theme]);
  return (
    <button
      className="theme-toggle label"
      onClick={() => setTheme(NEXT[theme])}
      title="Switch between system, light (paper) and dark (cabinet) themes"
    >
      <span aria-hidden="true" className={`theme-dot theme-${theme}`} />
      {theme === "system" ? "auto" : theme === "light" ? "paper" : "cabinet"}
    </button>
  );
}

/** How far the page is through its life cycle: its own stage, plus how far it has been scrolled. */
function useLife() {
  const { pathname } = useLocation();
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    window.scrollTo(0, 0); // every page starts at the top, and so at its own stage
  }, [pathname]);

  useEffect(() => {
    let frame = 0;
    const read = () => {
      frame = 0;
      const span = document.documentElement.scrollHeight - window.innerHeight;
      setProgress(span > 40 ? window.scrollY / span : 0);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [pathname]);

  return lifeAt(baseLife(pathname), progress);
}

export function Layout() {
  useAliveCabinet();
  const { pathname } = useLocation();
  const life = useLife();
  const [shell, setShell] = useState({ x: 0, y: 0 });
  const onChrysalis = useCallback((x: number, y: number) => setShell({ x, y }), []);
  return (
    <div className="shell">
      <Habitat life={life} home={pathname === "/"} />
      <Lamp />
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <NavLink to="/" className="wordmark" aria-label="Metamorph home">
          <span className="wordmark-mark" aria-hidden="true">
            <i />
            <i />
          </span>
          Metamorph
        </NavLink>
        <LifeScale life={life} />
        <nav className="nav" aria-label="Main">
          <NavLink to="/runs">Accessions</NavLink>
          <NavLink to="/relations">Collection</NavLink>
          <NavLink to="/lab">Lab</NavLink>
        </nav>
        <ThemeToggle />
        <LifeCycle life={life} onChrysalis={onChrysalis} />
      </header>
      {/* Wait for the shell's position, so the butterfly really does leave the chrysalis. */}
      <Butterfly free={creature(life).butterfly && shell.x > 0} from={shell} />
      {READ_ONLY && (
        <p className="demo-note label">
          Read-only demo · a frozen snapshot of the CV demo · nothing you do here is saved
        </p>
      )}
      <main id="main" className="page">
        <Outlet />
      </main>
      <footer className="colophon caption">
        <span>
          Metamorph tests LLM applications without labelled answers, by checking relations between outputs.
        </span>
        <span>
          Plates: Maria Sibylla Merian, <i>Metamorphosis insectorum Surinamensium</i> (1705). Public domain.
        </span>
      </footer>
    </div>
  );
}
