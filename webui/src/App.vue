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

import { 
  Activity, 
  Globe, 
  Settings, 
  Bell, 
  FileText, 
  Github 
} from "lucide-vue-next";

const nav = [
  { to: "/", label: "站点状态", icon: Activity },
  { to: "/sites", label: "站点管理", icon: Globe },
  { to: "/config", label: "服务配置", icon: Settings },
  { to: "/notifications", label: "通知设置", icon: Bell },
  { to: "/logs", label: "日志", icon: FileText },
];

function isActive(to: string) {
  return route.path === to;
}
</script>

<template>
  <div class="min-h-screen">

    <header class="sticky top-0 z-50 w-full border-b border-slate-200/50 glass dark:border-slate-800/50">
      <div class="container mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        <!-- Logo -->
        <RouterLink to="/" class="flex items-center gap-2 transition-opacity hover:opacity-80">
          <Activity class="h-6 w-6 text-brand-600 dark:text-brand-400" />
          <h1 class="text-xl font-bold tracking-tight text-slate-800 dark:text-white">
            PT Invite Watcher
          </h1>
        </RouterLink>

        <!-- Desktop Nav -->
        <nav class="hidden flex-1 items-center justify-end gap-1 md:flex">
          <RouterLink
            v-for="item in nav"
            :key="item.to"
            :to="item.to"
            class="group flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-slate-600 transition-all hover:bg-slate-100 hover:text-slate-900 active:scale-95 dark:text-slate-300 dark:hover:bg-slate-800/50 dark:hover:text-white"
            active-class="bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
          >
            <component
              :is="item.icon"
              class="h-4 w-4 transition-transform group-hover:scale-110 group-active:scale-95"
            />
            {{ item.label }}
          </RouterLink>
          
           <!-- Theme Picker & Toggle -->
           <div class="ml-4 flex items-center gap-2 border-l border-slate-200 pl-4 dark:border-slate-700">
              <ThemeToggle />
           </div>
        </nav>
      </div>
    </header>

    <main class="container mx-auto max-w-7xl flex-1 px-4 py-8 pb-24 md:pb-8">
     <RouterView v-slot="{ Component }">
      <Transition name="fade-slide" mode="out-in">
        <component :is="Component" />
      </Transition>
    </RouterView>
  </main>
  
    <!-- Cloud Bottom Nav (Mobile) -->
    <nav class="fixed bottom-0 z-40 flex w-full justify-around border-t border-slate-200/80 bg-white/80 px-2 py-2 backdrop-blur-md supports-[backdrop-filter]:bg-white/60 dark:border-slate-800/80 dark:bg-slate-950/80 dark:supports-[backdrop-filter]:bg-slate-950/60 sm:hidden">
      <RouterLink
        v-for="item in nav"
        :key="item.to"
        :to="item.to"
        class="flex flex-1 flex-col items-center justify-center gap-0.5 rounded-xl py-1 text-[10px] font-medium transition-colors active:scale-95"
        :class="
          isActive(item.to)
            ? 'text-brand-600 dark:text-brand-400'
            : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800/50'
        "
      >
        <component :is="item.icon" class="h-6 w-6" :stroke-width="isActive(item.to) ? 2.5 : 2" />
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>

    <!-- Toast Queue -->
    <div class="fixed bottom-24 right-5 z-50 flex flex-col-reverse gap-2 sm:bottom-5">
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
