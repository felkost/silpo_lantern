// G10: the one control on the shared header -- a sun/moon switch, no
// caption (the author's call). Writes `data-theme` on the root so an
// explicit choice wins over `prefers-color-scheme` in both directions
// (console.css guards its dark block on `:not([data-theme="light"])`).
// Remembered in localStorage inside try/catch: a blocked-storage context
// throws on write and must not take the toggle with it.

import { useState } from "react";

const KEY = "lantern_theme";

type Theme = "light" | "dark";

function read(): Theme | null {
  try {
    const stored = localStorage.getItem(KEY);
    return stored === "dark" || stored === "light" ? stored : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

function apply(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // remembered for this page only
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = read();
    if (stored !== null) {
      document.documentElement.setAttribute("data-theme", stored);
      return stored;
    }
    return systemTheme();
  });
  const dark = theme === "dark";
  const next: Theme = dark ? "light" : "dark";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label={`Theme: switch to ${next}`}
      className={dark ? "theme-switch on" : "theme-switch"}
      onClick={() => {
        apply(next);
        setTheme(next);
      }}
    >
      <svg className="sun" viewBox="0 0 24 24" aria-hidden="true" width="14" height="14">
        <circle cx="12" cy="12" r="4" fill="currentColor" />
        <g stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <line x1="12" y1="2" x2="12" y2="5" />
          <line x1="12" y1="19" x2="12" y2="22" />
          <line x1="2" y1="12" x2="5" y2="12" />
          <line x1="19" y1="12" x2="22" y2="12" />
          <line x1="4.9" y1="4.9" x2="7" y2="7" />
          <line x1="17" y1="17" x2="19.1" y2="19.1" />
          <line x1="4.9" y1="19.1" x2="7" y2="17" />
          <line x1="17" y1="7" x2="19.1" y2="4.9" />
        </g>
      </svg>
      <span className="knob" />
      <svg className="moon" viewBox="0 0 24 24" aria-hidden="true" width="14" height="14">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" fill="currentColor" />
      </svg>
    </button>
  );
}
