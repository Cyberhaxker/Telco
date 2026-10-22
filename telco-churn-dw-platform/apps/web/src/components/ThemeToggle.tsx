"use client";

import { useEffect, useState } from "react";

type Theme = "system" | "light" | "dark";
const LABEL: Record<Theme, string> = { system: "Auto", light: "Light", dark: "Dark" };

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");
  useEffect(() => {
    const saved = (localStorage.getItem("telco.theme") as Theme | null) ?? "system";
    setTheme(saved);
  }, []);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    localStorage.setItem("telco.theme", theme);
  }, [theme]);
  const next: Theme = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
  return (
    <button type="button" className="btn small" onClick={() => setTheme(next)} aria-label={`Theme: ${LABEL[theme]}. Switch to ${LABEL[next]}`}>
      Theme: {LABEL[theme]}
    </button>
  );
}
