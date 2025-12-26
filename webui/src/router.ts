import type { RouteRecordRaw } from "vue-router";

import DashboardPage from "./pages/DashboardPage.vue";
import SitesPage from "./pages/SitesPage.vue";
import ConfigPage from "./pages/ConfigPage.vue";
import NotificationsPage from "./pages/NotificationsPage.vue";

export const routes: RouteRecordRaw[] = [
  { path: "/", component: DashboardPage },
  { path: "/sites", component: SitesPage },
  { path: "/config", component: ConfigPage },
  { path: "/notifications", component: NotificationsPage },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];
