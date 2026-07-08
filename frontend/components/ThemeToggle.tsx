"use client";

import { useEffect, useState } from "react";

type Theme = "dark" | "light";

/** Background theme switch. The choice persists in localStorage and is applied
 *  before first paint by the inline script in app/layout.tsx. */
export default function ThemeToggle() {
  // Render a stable placeholder until mounted — the real theme is only
  // knowable on the client (localStorage), so this avoids hydration drift.
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const current = document.documentElement.dataset.theme;
    setTheme(current === "light" ? "light" : "dark");
  }, []);

  function toggle() {
    const next: Theme = theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* storage unavailable (private mode) — theme still applies for the session */
    }
    setTheme(next);
  }

  return (
    <button
      onClick={toggle}
      aria-label="Switch background theme"
      title="Switch background theme"
      className="rounded border border-line bg-ink-800 px-2.5 py-1 text-xs text-paper-dim transition-colors hover:border-gold-dim hover:text-gold"
    >
      {theme === null ? "◐" : theme === "dark" ? "◐ Light" : "◑ Dark"}
    </button>
  );
}
