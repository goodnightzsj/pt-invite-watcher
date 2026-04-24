import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";

import App from "./App.vue";
import OnboardingPage from "./pages/OnboardingPage.vue";
import { prefetchSecondaryPages, routes } from "./router";
import { initTheme } from "./theme";
import { loadRuntimeConfig, needsOnboarding } from "./runtime_config";

import "./styles.css";

// Seed runtime apiBase / wsBase / credentials from (1) the Tauri shell's
// bootstrap injection, (2) prior Onboarding state in localStorage, or (3)
// same-origin fallback. Must happen before the router / components mount so
// the first fetch doesn't race against a not-yet-configured state.
loadRuntimeConfig();

const router = createRouter({
  history: createWebHistory(),
  // Inject a catch-all Onboarding route at the top when the Tauri shell says
  // we're unconfigured remote-mode. Browser deployments never match this —
  // `needsOnboarding()` returns false outside Tauri.
  routes: needsOnboarding()
    ? [{ path: "/:_all*", component: OnboardingPage }]
    : routes,
});

initTheme();

createApp(App).use(router).mount("#app");

// Skip chunk prefetch during Onboarding — the user hasn't authenticated yet
// and we don't want to ping an unknown server 4 extra times.
if (!needsOnboarding()) {
  prefetchSecondaryPages();
}

