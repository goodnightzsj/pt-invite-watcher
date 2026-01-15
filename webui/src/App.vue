<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from "vue-router";
import { onMounted, ref } from "vue";
import { api } from "./api";

import ThemeToggle from "./components/ThemeToggle.vue";
import Toast from "./components/Toast.vue";
import MobileNav from "./components/MobileNav.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import { toasts, removeToast } from "./toast";

import {
  Activity,
  Globe,
  Settings,
  Bell,
  FileText,
  Github
} from "lucide-vue-next";

const route = useRoute();

const nav = [
  { to: "/", label: "站点状态", icon: Activity },
  { to: "/sites", label: "站点管理", icon: Globe },
  { to: "/config", label: "服务配置", icon: Settings },
  { to: "/notifications", label: "通知设置", icon: Bell },
  { to: "/logs", label: "日志", icon: FileText },
];

const version = ref("");

onMounted(async () => {
  try {
    const resp = await api.version();
    version.value = resp.version;
  } catch (e) {
    // ignore
  }
});
</script>

<template>
  <div class="min-h-screen relative overflow-x-hidden">
    <div class="ui-aurora" aria-hidden="true"></div>

    <header class="sticky top-0 z-50 w-full glass border-x-0 border-t-0 rounded-none">
      <div class="container mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        <!-- Logo -->
        <RouterLink to="/" class="flex items-center gap-2 transition-opacity hover:opacity-80">
          <Activity class="h-6 w-6 text-brand-600 dark:text-brand-400" />
          <h1 class="text-xl font-bold tracking-tight text-slate-800 dark:text-white">
            PT Invite Watcher
            <span v-if="version" class="ml-2 text-xs font-medium text-slate-500/80">v{{ version }}</span>
          </h1>
        </RouterLink>

        <!-- Right Side: Nav (Desktop) + Actions (Global) -->
        <div class="flex items-center gap-3 sm:gap-4">
          <!-- Desktop Nav Links -->
          <nav class="hidden items-center gap-1 md:flex">
            <RouterLink v-for="item in nav" :key="item.to" :to="item.to"
              class="group flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-slate-600 transition-all hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white"
              active-class="bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300 shadow-sm">
              <component :is="item.icon" class="h-4 w-4 transition-transform group-hover:-translate-y-0.5" />
              {{ item.label }}
            </RouterLink>
          </nav>

          <!-- Divider (Desktop only) -->
          <div class="hidden h-5 w-px bg-slate-200 dark:bg-white/10 md:block"></div>

          <!-- Global Actions (Auto-Dark, GitHub) -->
          <div class="flex items-center gap-2">
            <a href="https://github.com/goodnightzsj/pt-invite-watcher" target="_blank"
              class="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 transition-all hover:border-brand-300 hover:shadow-md dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-white/20">
              <Github class="h-5 w-5" />
            </a>
            <ThemeToggle />
          </div>
        </div>
      </div>
    </header>

    <main class="container mx-auto max-w-7xl flex-1 px-4 py-8 pb-24 md:pb-8">
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>

    <!-- Cloud Bottom Nav (Mobile) -->
    <!-- Cloud Bottom Nav (Mobile) -->
    <MobileNav :items="nav" />

    <!-- Toast Queue -->
    <div class="fixed bottom-24 right-5 z-50 flex flex-col-reverse gap-2 sm:bottom-5">
      <transition-group name="list">
        <Toast v-for="t in toasts" :key="t.id" :kind="t.kind" @close="removeToast(t.id)">
          {{ t.message }}
        </Toast>
      </transition-group>
      <!-- Global Confirm Dialog -->
      <ConfirmDialog />
    </div>
  </div>
</template>

<style scoped>
/* Scoped styles removed in favor of global styles.css */
</style>
