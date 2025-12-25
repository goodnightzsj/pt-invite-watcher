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
  { to: "/config", label: "服务配置" },
  { to: "/notifications", label: "通知设置" },
];

function isActive(to: string) {
  return route.path === to;
}
</script>

<template>
  <div class="min-h-screen">
    <header class="sticky top-0 z-40 border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-950/70">
      <div class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900">
            PT
          </div>
          <div>
            <div class="text-base font-semibold">PT Invite Watcher</div>
            <div class="text-xs text-slate-500 dark:text-slate-400">MoviePilot 站点来源 · NexusPHP 探测 · Web UI 配置</div>
          </div>
        </div>

        <nav class="flex flex-wrap items-center gap-2">
          <RouterLink
            v-for="item in nav"
            :key="item.to"
            :to="item.to"
            class="rounded-xl px-3 py-2 text-sm font-medium transition"
            :class="
              isActive(item.to)
                ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                : 'text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800'
            "
          >
            {{ item.label }}
          </RouterLink>
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            class="rounded-xl px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            API Docs
          </a>
        </nav>

        <div class="flex items-center gap-3">
          <Badge label="主题" tone="slate" />
          <select
            v-model="theme"
            class="rounded-xl border-slate-200 bg-white text-sm text-slate-800 shadow-sm focus:border-slate-300 focus:ring-slate-300 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-700 dark:focus:ring-slate-700"
          >
            <option value="system">跟随系统</option>
            <option value="light">浅色</option>
            <option value="dark">深色</option>
          </select>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-7xl px-4 py-6">
      <RouterView />
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

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

