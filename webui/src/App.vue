<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";

import Badge from "./components/Badge.vue";
import { getThemeMode, setThemeMode, type ThemeMode } from "./theme";
import { toast } from "./toast";

const route = useRoute();

const theme = computed({
  get: () => getThemeMode(),
  set: (v: ThemeMode) => setThemeMode(v),
});

const nav = [
  { to: "/", label: "站点状态" },
  { to: "/sites", label: "站点管理" },
  { to: "/config", label: "服务配置" },
  { to: "/notifications", label: "通知设置" },
];

function isActive(to: string) {
  return route.path === to;
}
</script>

<template>
  <div class="min-h-screen">
    <header class="sticky top-0 z-40 border-b border-slate-200/80 bg-white/70 backdrop-blur-md supports-[backdrop-filter]:bg-white/60 dark:border-slate-800/80 dark:bg-slate-950/70 dark:supports-[backdrop-filter]:bg-slate-950/60">
      <div class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-md shadow-indigo-500/20 ring-1 ring-white/20">
            <span class="font-bold">PT</span>
          </div>
          <div>
            <div class="bg-gradient-to-r from-slate-900 to-slate-600 bg-clip-text text-base font-bold text-transparent dark:from-white dark:to-slate-400">
              PT Invite Watcher
            </div>
            <div class="text-xs font-medium text-slate-500 dark:text-slate-500">
              MoviePilot 站点来源 · NexusPHP 探测
            </div>
          </div>
        </div>

        <nav class="flex flex-wrap items-center gap-1">
          <RouterLink
            v-for="item in nav"
            :key="item.to"
            :to="item.to"
            class="rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200"
            :class="
              isActive(item.to)
                ? 'bg-indigo-50 text-indigo-700 shadow-sm ring-1 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/20'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
            "
          >
            {{ item.label }}
          </RouterLink>
          <div class="mx-2 h-4 w-px bg-slate-200 dark:bg-slate-800"></div>
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            class="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            API Docs
          </a>
        </nav>

        <div class="flex items-center gap-3">
          <select
            v-model="theme"
            class="cursor-pointer rounded-lg border-none bg-slate-100 py-1.5 pl-3 pr-8 text-sm font-medium text-slate-700 transition hover:bg-slate-200 focus:ring-2 focus:ring-indigo-500/20 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <option value="system">跟随系统</option>
            <option value="light">浅色模式</option>
            <option value="dark">深色模式</option>
          </select>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-7xl px-4 py-8">
      <RouterView v-slot="{ Component }">
        <transition name="fade-page" mode="out-in">
          <component :is="Component" />
        </transition>
      </RouterView>
    </main>

    <transition name="fade">
      <div
        v-if="toast.open"
        class="fixed bottom-5 right-5 z-50 max-w-sm rounded-2xl border px-4 py-3 text-sm shadow-lg"
        :class="
          toast.kind === 'success'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200'
            : toast.kind === 'error'
            ? 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200'
            : 'border-slate-200 bg-white text-slate-800 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100'
        "
      >
        {{ toast.message }}
      </div>
    </transition>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

.fade-page-enter-active,
.fade-page-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-page-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.fade-page-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
