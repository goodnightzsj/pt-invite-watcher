<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from "vue-router";

import ThemeToggle from "./components/ThemeToggle.vue";
import { toasts, removeToast, type ToastKind } from "./toast";

function toastClasses(kind: ToastKind): string {
  if (kind === 'success') {
    return 'border-success-200 bg-success-50 text-success-800 dark:border-success-900 dark:bg-success-950/40 dark:text-success-200';
  } else if (kind === 'error') {
    return 'border-danger-200 bg-danger-50 text-danger-800 dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-200';
  }
  return 'border-slate-200 bg-white text-slate-800 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100';
}

const route = useRoute();

const nav = [
  { to: "/", label: "站点状态" },
  { to: "/sites", label: "站点管理" },
  { to: "/config", label: "服务配置" },
  { to: "/notifications", label: "通知设置" },
  { to: "/logs", label: "日志" },
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
          <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 text-white shadow-md shadow-brand-500/20 ring-1 ring-white/20">
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
                ? 'bg-brand-50 text-brand-700 shadow-sm ring-1 ring-brand-200 dark:bg-brand-500/10 dark:text-brand-300 dark:ring-brand-500/20'
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
          <a
            href="https://github.com/goodnightzsj/pt-invite-watcher"
            target="_blank"
            rel="noreferrer"
            class="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            title="GitHub"
          >
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path
                fill-rule="evenodd"
                clip-rule="evenodd"
                d="M12 2C6.477 2 2 6.486 2 12.021c0 4.427 2.865 8.182 6.839 9.504.5.092.682-.217.682-.483 0-.237-.009-.868-.014-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.907-.62.069-.608.069-.608 1.003.071 1.531 1.033 1.531 1.033.892 1.53 2.341 1.088 2.91.832.091-.647.35-1.089.636-1.339-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.271.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.748-1.026 2.748-1.026.546 1.379.203 2.397.1 2.65.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.852 0 1.337-.012 2.417-.012 2.747 0 .268.18.579.688.481A10.02 10.02 0 0 0 22 12.021C22 6.486 17.523 2 12 2Z"
              />
            </svg>
            GitHub
          </a>
        </nav>

        <div class="flex items-center gap-3">
          <ThemeToggle />
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

    <!-- Toast Queue -->
    <div class="fixed bottom-5 right-5 z-50 flex flex-col-reverse gap-2">
      <transition-group name="fade">
        <div
          v-for="t in toasts"
          :key="t.id"
          class="max-w-sm rounded-2xl border px-4 py-3 text-sm shadow-lg cursor-pointer"
          :class="toastClasses(t.kind)"
          @click="removeToast(t.id)"
        >
          {{ t.message }}
        </div>
      </transition-group>
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease, transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateX(40px);
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
