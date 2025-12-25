import type { RouteRecordRaw } from "vue-router";

import DashboardPage from "./pages/DashboardPage.vue";
import ConfigPage from "./pages/ConfigPage.vue";
import NotificationsPage from "./pages/NotificationsPage.vue";

export const routes: RouteRecordRaw[] = [
  { path: "/", component: DashboardPage },
  { path: "/config", component: ConfigPage },
  { path: "/notifications", component: NotificationsPage },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

