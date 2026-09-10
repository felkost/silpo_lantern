// G10: the one control on the shared header. Writes `data-theme` on the
// root so an explicit choice wins over `prefers-color-scheme` in both
// directions (console.css guards its dark block on `:not([data-theme=
// "light"])`). Remembered in localStorage inside try/catch: a blocked-
// storage context throws on write and must not take the toggle with it.

import { useState } from "react";

const KEY = "lantern_theme";

function read(): "light" | "dark" | null {
  try {
    const stored = localStorage.getItem(KEY);
    return stored === "dark" || stored === "light" ? stored : null;
  } catch {
    return null;
  }
}

function apply(theme: "light" | "dark"): void {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // remembered for this page only
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark" | null>(() => {
    const stored = read();
    if (stored !== null) {
      document.documentElement.setAttribute("data-theme", stored);
    }
    return stored;
  });
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" className="quiet" onClick={() => { apply(next); setTheme(next); }}>
      Theme: {next}
    </button>
  );
}
