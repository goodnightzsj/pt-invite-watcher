/**
 * Vue i18n instance.
 *
 * Scope: foundation + navigation / onboarding / common buttons / toasts.
 * Page-level detail strings (site table content, scanner reason codes) stay
 * hardcoded for now — migrating all ~500 strings is a bigger effort. The
 * foundation below lets anyone extend by adding keys + locales without
 * touching plumbing.
 *
 * Persistence: language choice lives in localStorage. First-load falls back
 * to navigator.language prefix (`zh` → zh-CN, everything else → en-US).
 */
import { createI18n } from "vue-i18n";

import zhCN from "./zh-CN";
import enUS from "./en-US";

export type Locale = "zh-CN" | "en-US";

const STORAGE_KEY = "ptiw_locale";

function detectLocale(): Locale {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved === "zh-CN" || saved === "en-US") return saved;
    } catch { /* private mode */ }
    const nav = (navigator.language || "zh").toLowerCase();
    return nav.startsWith("zh") ? "zh-CN" : "en-US";
}

export const i18n = createI18n({
    legacy: false,        // composition API
    globalInjection: true, // `$t` available in templates
    locale: detectLocale(),
    fallbackLocale: "zh-CN",
    messages: {
        "zh-CN": zhCN,
        "en-US": enUS,
    },
});

export function setLocale(locale: Locale): void {
    i18n.global.locale.value = locale;
    try { localStorage.setItem(STORAGE_KEY, locale); } catch { /* ignore */ }
    document.documentElement.setAttribute("lang", locale);
}

export function getLocale(): Locale {
    return i18n.global.locale.value as Locale;
}

// Sync the <html lang=""> attr to the detected locale at boot so screen
// readers + search engines see the right language.
document.documentElement.setAttribute("lang", (i18n.global.locale.value as string));
