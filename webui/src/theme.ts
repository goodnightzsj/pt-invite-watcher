export type ThemeMode = "system" | "light" | "dark";

const STORAGE_KEY = "ptiw_theme";

function getPreferredTheme(): ThemeMode {
  const raw = (localStorage.getItem(STORAGE_KEY) || "system").toLowerCase();
  if (raw === "light" || raw === "dark" || raw === "system") return raw;
  return "system";
}

function prefersDark(): boolean {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(mode: ThemeMode) {
  const html = document.documentElement;
  const dark = mode === "dark" || (mode === "system" && prefersDark());
  html.classList.toggle("dark", dark);
}

export function initTheme() {
  applyTheme(getPreferredTheme());
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      const mode = getPreferredTheme();
      if (mode === "system") applyTheme(mode);
    });
  }
}

export function getThemeMode(): ThemeMode {
  return getPreferredTheme();
}

export function setThemeMode(mode: ThemeMode) {
  localStorage.setItem(STORAGE_KEY, mode);
  applyTheme(mode);
}

