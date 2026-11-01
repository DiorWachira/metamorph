import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useStored } from "../hooks";

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

export function Layout() {
  return (
    <div className="shell">
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
        <nav className="nav" aria-label="Main">
          <NavLink to="/runs">Accessions</NavLink>
          <NavLink to="/relations">Collection</NavLink>
          <NavLink to="/lab">Lab</NavLink>
        </nav>
        <ThemeToggle />
      </header>
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
