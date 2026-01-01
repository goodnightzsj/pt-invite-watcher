<script setup lang="ts">
import { ref } from "vue";
import { getThemeMode, setThemeMode, type ThemeMode } from "../theme";

const theme = ref<ThemeMode>(getThemeMode());

const modes: ThemeMode[] = ["system", "light", "dark"];

function cycleTheme() {
  const currentIndex = modes.indexOf(theme.value);
  const nextIndex = (currentIndex + 1) % modes.length;
  const nextMode = modes[nextIndex];
  setThemeMode(nextMode);
  theme.value = nextMode;
}

const themeLabels: Record<ThemeMode, string> = {
  system: "跟随系统",
  light: "浅色模式",
  dark: "深色模式",
};
</script>

<template>
  <button
    class="theme-toggle-btn relative flex h-9 w-9 items-center justify-center rounded-lg text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
    :title="`当前主题: ${themeLabels[theme]}`"
    @click="cycleTheme"
    aria-label="切换主题"
  >
    <div class="relative h-5 w-5 overflow-hidden">
      <!-- System: Monitor icon -->
      <div
        class="theme-icon absolute inset-0 flex items-center justify-center transition-all duration-300"
        :class="{
          'translate-y-0 opacity-100': theme === 'system',
          '-translate-y-full opacity-0': theme === 'light',
          'translate-y-full opacity-0': theme === 'dark',
        }"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect width="20" height="14" x="2" y="3" rx="2"/>
          <line x1="8" x2="16" y1="21" y2="21"/>
          <line x1="12" x2="12" y1="17" y2="21"/>
        </svg>
      </div>

      <!-- Light: Sun icon -->
      <div
        class="theme-icon absolute inset-0 flex items-center justify-center text-warning-500 transition-all duration-300"
        :class="{
          'translate-y-0 opacity-100': theme === 'light',
          'translate-y-full opacity-0': theme === 'system',
          '-translate-y-full opacity-0': theme === 'dark',
        }"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="4"/>
          <path d="M12 2v2"/>
          <path d="M12 20v2"/>
          <path d="m4.93 4.93 1.41 1.41"/>
          <path d="m17.66 17.66 1.41 1.41"/>
          <path d="M2 12h2"/>
          <path d="M20 12h2"/>
          <path d="m6.34 17.66-1.41 1.41"/>
          <path d="m19.07 4.93-1.41 1.41"/>
        </svg>
      </div>

      <!-- Dark: Moon icon -->
      <div
        class="theme-icon absolute inset-0 flex items-center justify-center text-brand-400 transition-all duration-300"
        :class="{
          'translate-y-0 opacity-100': theme === 'dark',
          '-translate-y-full opacity-0': theme === 'system',
          'translate-y-full opacity-0': theme === 'light',
        }"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
        </svg>
      </div>
    </div>
  </button>
</template>

<style scoped>
.theme-toggle-btn:focus {
  outline: none;
}
.theme-toggle-btn:focus-visible {
  outline: none;
}

.theme-icon {
  transition-timing-function: cubic-bezier(0.23, 1, 0.32, 1);
}
</style>
