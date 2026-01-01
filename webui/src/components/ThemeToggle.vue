<script setup lang="ts">
import { ref } from "vue";
import { getThemeMode, setThemeMode, type ThemeMode } from "../theme";
import { Monitor, Sun, Moon } from "lucide-vue-next";

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
        <Monitor :size="20" />
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
        <Sun :size="20" />
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
        <Moon :size="20" />
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
