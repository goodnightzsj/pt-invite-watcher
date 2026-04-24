<script setup lang="ts">
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { onMounted, onUnmounted, ref } from "vue";
import { api } from "./api";

import ThemeToggle from "./components/ThemeToggle.vue";
import Toast from "./components/Toast.vue";
import MobileNav from "./components/MobileNav.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import CommandPalette from "./components/CommandPalette.vue";
import UpdateBanner from "./components/UpdateBanner.vue";
import { toasts, removeToast } from "./toast";
import { registerCommands } from "./commands";
import { clearIconCache } from "./icon_cache";
import { setThemeMode } from "./theme";
import { showToast } from "./toast";
import { maybeInitSentry } from "./sentry";

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

const router = useRouter();
let unregisterCommands: (() => void) | undefined;

onMounted(async () => {
  try {
    const resp = await api.version();
    version.value = resp.version;
  } catch (e) {
    // ignore
  }
  // Kick off Sentry init in the background (lazy dynamic import). No-op when
  // the server isn't configured with a frontend DSN. Doesn't block render.
  try {
    const cfg = await api.configGet();
    if (cfg?.observability?.sentry_dsn) {
      void maybeInitSentry(cfg.observability.sentry_dsn);
    }
  } catch {
    /* config probe failing is non-fatal — we'll retry on next interaction */
  }

  // Register global commands — nav to each route, theme toggles, icon cache
  // clear, scan trigger (via custom window event the Dashboard listens for).
  // Command palette (Cmd/Ctrl+K) surfaces all of these with fuzzy search.
  unregisterCommands = registerCommands([
    { id: "nav.dashboard", label: "打开 · 站点状态", category: "导航", aliases: ["dashboard", "home", "主页"], shortcut: "⌘1", run: () => router.push("/") },
    { id: "nav.sites", label: "打开 · 站点管理", category: "导航", aliases: ["sites", "manage"], shortcut: "⌘2", run: () => router.push("/sites") },
    { id: "nav.config", label: "打开 · 服务配置", category: "导航", aliases: ["config", "settings", "设置"], shortcut: "⌘3", run: () => router.push("/config") },
    { id: "nav.notifications", label: "打开 · 通知设置", category: "导航", aliases: ["notifications", "alerts"], shortcut: "⌘4", run: () => router.push("/notifications") },
    { id: "nav.logs", label: "打开 · 日志", category: "导航", aliases: ["logs", "events"], shortcut: "⌘5", run: () => router.push("/logs") },
    {
      id: "action.scan", label: "立即扫描全部站点", category: "操作", aliases: ["scan", "refresh"], shortcut: "⌘⇧R",
      run: () => { window.dispatchEvent(new CustomEvent("ptiw:scan-now")); showToast("已触发扫描", "info", 1600); },
    },
    {
      id: "action.clear-icon-cache", label: "清除站点图标缓存", category: "操作", aliases: ["icons", "favicon"],
      run: () => { clearIconCache(); showToast("图标缓存已清除", "success", 1600); },
    },
    { id: "theme.light", label: "主题 · 日间模式", category: "设置", aliases: ["light", "day"], run: () => { setThemeMode("light"); } },
    { id: "theme.dark", label: "主题 · 夜间模式", category: "设置", aliases: ["dark", "night"], run: () => { setThemeMode("dark"); } },
    { id: "theme.system", label: "主题 · 跟随系统", category: "设置", aliases: ["system", "auto"], run: () => { setThemeMode("system"); } },
  ]);
});

onUnmounted(() => {
  unregisterCommands?.();
});
</script>

<template>
  <!-- `overflow-x: clip` (not `hidden`) keeps sticky descendants attached to the viewport
       instead of the layout wrapper — `hidden` turns the wrapper into a scroll container,
       which pins `sticky top-0` to the wrapper top rather than the window. -->
  <div class="min-h-screen relative [overflow-x:clip]">
    <div class="ui-aurora" aria-hidden="true"></div>

    <!-- `pt-safe` gives us the iOS status-bar inset when running in the Capacitor
         shell (normally 44-54px). Browser + Tauri see `env(safe-area-inset-top)`
         as 0 and the fallback 0.5rem keeps the header from hugging the window
         chrome on desktop. `pl-safe` / `pr-safe` handle landscape iPhone where
         the notch eats screen edges. -->
    <!-- Self-update banner (Tauri desktop only). Sits above the header so
         users see it regardless of which page they're on. -->
    <UpdateBanner />

    <header class="sticky top-0 z-50 w-full glass border-x-0 border-t-0 rounded-none pt-safe pl-safe pr-safe">
      <div class="container mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        <!-- Logo — the brand chip uses the theme accent with a soft glow so the app identity is
             present without repeating a heavy gradient on every surface. -->
        <RouterLink to="/" class="group flex items-center gap-3 transition-opacity hover:opacity-90">
          <span
            class="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-600 text-white shadow-md shadow-brand-500/30 ring-1 ring-inset ring-white/30 dark:ring-white/10"
          >
            <Activity class="h-5 w-5" />
            <span class="pointer-events-none absolute inset-0 rounded-xl bg-white/0 transition-colors duration-200 group-hover:bg-white/10" aria-hidden="true" />
          </span>
          <div class="leading-tight">
            <h1 class="text-base font-bold tracking-tight text-slate-900 dark:text-white">
              PT Invite Watcher
            </h1>
            <div v-if="version" class="mt-0.5 text-[11px] font-medium text-slate-500 tabular-nums dark:text-slate-400">v{{ version }}</div>
          </div>
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
              class="host-hide-mobile flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 transition-all hover:border-brand-300 hover:shadow-md dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-white/20"
              aria-label="GitHub 仓库">
              <Github class="h-5 w-5" />
            </a>
            <ThemeToggle />
          </div>
        </div>
      </div>
    </header>

    <!-- `pb-[calc(6rem+env(safe-area-inset-bottom))]` keeps mobile content above
         the floating Dock even on devices with a home-indicator bar. -->
    <main class="container mx-auto max-w-7xl flex-1 px-4 py-8 pb-[calc(6rem+env(safe-area-inset-bottom))] md:pb-8">
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>

    <!-- Cloud Bottom Nav (Mobile) -->
    <!-- Cloud Bottom Nav (Mobile) -->
    <MobileNav :items="nav" />

    <!-- Command palette (Cmd/Ctrl+K). Lives at app root so it's always
         available regardless of which route is mounted. -->
    <CommandPalette />

    <!-- Toast Queue — inset by safe-area so home-indicator on iPhone doesn't
         swallow the first toast. Desktop + browser fall back to the 24/5 rem. -->
    <div class="fixed right-5 bottom-[calc(6rem+env(safe-area-inset-bottom))] z-50 flex flex-col-reverse gap-2 sm:bottom-[calc(1.25rem+env(safe-area-inset-bottom))]">
      <transition-group name="list">
        <Toast v-for="t in toasts" :key="t.id" :kind="t.kind" @close="removeToast(t.id)">
          {{ t.message }}<span v-if="t.count > 1" class="ml-2 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-black/10 px-1.5 text-[11px] font-semibold tabular-nums dark:bg-white/15">×{{ t.count }}</span>
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
