import type { RouteRecordRaw } from "vue-router";

// Only the landing page is eager-imported — all other routes are code-split via dynamic
// import so the initial paint downloads only what the dashboard needs. Vite emits a preload
// link for each chunk so subsequent nav still happens in a single RTT.
import DashboardPage from "./pages/DashboardPage.vue";

// Factories for the lazy pages, so we can hand the same dynamic-import reference to both
// the router (for navigation) and the idle-preload warmer below (for latency). Without
// sharing the factory the two would trigger distinct chunk fetches.
const lazySites = () => import("./pages/SitesPage.vue");
const lazyConfig = () => import("./pages/ConfigPage.vue");
const lazyNotifications = () => import("./pages/NotificationsPage.vue");
const lazyLogs = () => import("./pages/LogsPage.vue");

export const routes: RouteRecordRaw[] = [
  { path: "/", component: DashboardPage },
  { path: "/sites", component: lazySites },
  { path: "/config", component: lazyConfig },
  { path: "/notifications", component: lazyNotifications },
  { path: "/logs", component: lazyLogs },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

/**
 * Prefetch the lazy route chunks after the dashboard has idled.
 *
 * The dashboard is interactive within ~one RTT, but switching to another page
 * still pays a chunk-fetch roundtrip. Warming the secondary chunks during the
 * browser's idle period means tab-navigation becomes instant on typical desktop
 * connections, at the cost of ~50KB of eager transfer (once, after TTI).
 *
 * `requestIdleCallback` is well-supported on Chromium/Firefox; we fall back to
 * a small setTimeout on Safari so users there still benefit. Errors are
 * swallowed — a prefetch that fails will simply refetch on navigation.
 */
export function prefetchSecondaryPages(): void {
    const warm = () => {
        void lazySites().catch(() => { });
        void lazyConfig().catch(() => { });
        void lazyNotifications().catch(() => { });
        void lazyLogs().catch(() => { });
    };
    const ric = (window as any).requestIdleCallback;
    if (typeof ric === "function") {
        ric(warm, { timeout: 3000 });
    } else {
        setTimeout(warm, 1500);
    }
}
