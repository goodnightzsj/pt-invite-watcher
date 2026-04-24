import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";

import App from "./App.vue";
import OnboardingPage from "./pages/OnboardingPage.vue";
import { prefetchSecondaryPages, routes } from "./router";
import { initTheme } from "./theme";
import { loadRuntimeConfig, needsOnboarding } from "./runtime_config";
import { applyHostAttribute, isCapacitor, syncStatusBar, wireHardwareBack } from "./capacitor_integration";

import "./styles.css";

// Seed runtime apiBase / wsBase / credentials from (1) the Tauri shell's
// bootstrap injection, (2) prior Onboarding state in localStorage, or (3)
// same-origin fallback. Must happen before the router / components mount so
// the first fetch doesn't race against a not-yet-configured state.
loadRuntimeConfig();

// Tag <html data-host="capacitor-ios|capacitor-android|tauri|browser"> so
// CSS rules can surgically adjust per shell (e.g. hide external links on
// mobile where opening a browser is clunky; add a drag region on Tauri).
applyHostAttribute();

const router = createRouter({
  history: createWebHistory(),
  // Inject a catch-all Onboarding route at the top when the Tauri shell says
  // we're unconfigured remote-mode. Browser deployments never match this —
  // `needsOnboarding()` returns false outside Tauri.
  routes: needsOnboarding()
    ? [{ path: "/:_all*", component: OnboardingPage }]
    : routes,
  // Always start at the top when navigating to a new page; restore saved
  // position when going back via browser/mobile back button. Without this
  // Vue Router leaves the scroll position wherever it was before nav, which
  // is jarring when pages have very different content lengths.
  scrollBehavior(_to, _from, savedPosition) {
    if (savedPosition) return savedPosition;
    return { top: 0, left: 0, behavior: "smooth" };
  },
});

// Dynamic page title — browser tab + PWA app switcher + Capacitor title bar
// reflect the current view. "PT Invite Watcher" alone is the root fallback
// so users arriving from a search still see the product name.
const BASE_TITLE = "PT Invite Watcher";
router.afterEach((to) => {
  const pageTitle = (to.meta?.title as string | undefined) || "";
  document.title = pageTitle ? `${pageTitle} · ${BASE_TITLE}` : BASE_TITLE;
});

// Keyboard-driven navigation for desktop + Tauri users. Cmd/Ctrl+1..5 jumps
// to the five main views; only active when no text input is focused so we
// don't hijack keystrokes mid-typing. Mobile users can't trigger these
// (no keyboard mod) so the listener is still safe to always install.
const NAV_KEY_TO_PATH: Record<string, string> = {
  "1": "/",
  "2": "/sites",
  "3": "/config",
  "4": "/notifications",
  "5": "/logs",
};
window.addEventListener("keydown", (e: KeyboardEvent) => {
  // Meta = macOS Cmd, Control = Windows/Linux Ctrl. Requiring both is out
  // because native menus own Cmd+1..5 on macOS — but in a webview we're
  // free to claim them.
  if (!(e.metaKey || e.ctrlKey)) return;
  if (e.altKey || e.shiftKey) return; // Leave Alt/Shift combos for the browser
  const target = e.target as HTMLElement | null;
  const tag = (target?.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
  const path = NAV_KEY_TO_PATH[e.key];
  if (!path) return;
  e.preventDefault();
  if (router.currentRoute.value.path !== path) {
    void router.push(path);
  }
});

initTheme();

createApp(App).use(router).mount("#app");

// Skip chunk prefetch during Onboarding — the user hasn't authenticated yet
// and we don't want to ping an unknown server 4 extra times.
if (!needsOnboarding()) {
  prefetchSecondaryPages();
}

// Capacitor-only wiring: zero-cost no-op in browser / Tauri shells. Hardware
// back button on Android routes through the Vue router; status bar tracks
// the current theme (dark/light) so icons stay legible over the glass header.
if (isCapacitor()) {
  wireHardwareBack(router);
  const isDark = document.documentElement.classList.contains("dark");
  syncStatusBar(isDark);
  // Re-sync whenever ThemeToggle flips the `dark` class.
  new MutationObserver(() => {
    syncStatusBar(document.documentElement.classList.contains("dark"));
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
}

