import type { RouteRecordRaw } from "vue-router";

// Only the landing page is eager-imported — all other routes are code-split via dynamic
// import so the initial paint downloads only what the dashboard needs. Vite emits a preload
// link for each chunk so subsequent nav still happens in a single RTT.
import DashboardPage from "./pages/DashboardPage.vue";

export const routes: RouteRecordRaw[] = [
  { path: "/", component: DashboardPage },
  { path: "/sites", component: () => import("./pages/SitesPage.vue") },
  { path: "/config", component: () => import("./pages/ConfigPage.vue") },
  { path: "/notifications", component: () => import("./pages/NotificationsPage.vue") },
  { path: "/logs", component: () => import("./pages/LogsPage.vue") },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];
