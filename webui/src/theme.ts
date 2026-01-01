export type ThemeMode = "system" | "light" | "dark";

const STORAGE_KEY = "ptiw_theme";
const STORAGE_ACCENT_KEY = "ptiw_accent";

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


export type AccentColor = "indigo" | "emerald" | "rose" | "amber" | "violet";

export const PALETTES: Record<AccentColor, Record<number, string>> = {
  indigo: {
    50: "238 242 255",
    100: "224 231 255",
    200: "199 210 254",
    300: "165 180 252",
    400: "129 140 248",
    500: "99 102 241",
    600: "79 70 229",
    700: "67 56 202",
    800: "55 48 163",
    900: "49 46 129",
    950: "30 27 75",
  },
  emerald: {
    50: "236 253 245",
    100: "209 250 229",
    200: "167 243 208",
    300: "110 231 183",
    400: "52 211 153",
    500: "16 185 129",
    600: "5 150 105",
    700: "4 120 87",
    800: "6 95 70",
    900: "6 78 59",
    950: "2 44 34",
  },
  rose: {
    50: "255 241 242",
    100: "255 228 230",
    200: "254 205 211",
    300: "253 164 175",
    400: "251 113 133",
    500: "244 63 94",
    600: "225 29 72",
    700: "190 18 60",
    800: "159 18 57",
    900: "136 19 55",
    950: "76 5 25",
  },
  amber: {
    50: "255 251 235",
    100: "254 243 199",
    200: "253 230 138",
    300: "252 211 77",
    400: "251 191 36",
    500: "245 158 11",
    600: "217 119 6",
    700: "180 83 9",
    800: "146 64 14",
    900: "120 53 15",
    950: "69 26 3",
  },
  violet: {
    50: "245 243 255",
    100: "237 233 254",
    200: "221 214 254",
    300: "196 181 253",
    400: "167 139 250",
    500: "139 92 246",
    600: "124 58 237",
    700: "109 40 217",
    800: "91 33 182",
    900: "76 29 149",
    950: "46 16 101",
  },
};

export function getAccentColor(): AccentColor {
  const raw = localStorage.getItem(STORAGE_ACCENT_KEY) as AccentColor;
  if (PALETTES[raw]) return raw;
  return "indigo";
}

export function setAccentColor(color: AccentColor) {
  const palette = PALETTES[color];
  if (!palette) return;

  const root = document.documentElement;
  Object.entries(palette).forEach(([shade, value]) => {
    root.style.setProperty(`--color-brand-${shade}`, value);
  });

  localStorage.setItem(STORAGE_ACCENT_KEY, color);
}

export function initTheme() {
  applyTheme(getPreferredTheme());
  setAccentColor(getAccentColor()); // Apply saved accent

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

