import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";

import App from "./App.vue";
import { prefetchSecondaryPages, routes } from "./router";
import { initTheme } from "./theme";

import "./styles.css";

const router = createRouter({
  history: createWebHistory(),
  routes,
});

initTheme();

createApp(App).use(router).mount("#app");

// Once the dashboard's initial chunk has settled, opportunistically pull down
// the other route chunks so nav between tabs is instant on typical networks.
prefetchSecondaryPages();

