import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";

import App from "./App.vue";
import { routes } from "./router";
import { initTheme } from "./theme";

import "./styles.css";

const router = createRouter({
  history: createWebHistory(),
  routes,
});

initTheme();

createApp(App).use(router).mount("#app");

