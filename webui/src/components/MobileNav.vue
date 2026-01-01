<script setup lang="ts">
import { RouterLink, useRoute } from "vue-router";
import { type Component } from "vue";

defineProps<{
  items: { 
    to: string; 
    label: string; 
    icon: Component 
  }[];
}>();

const route = useRoute();

function isActive(to: string) {
  return route.path === to;
}
</script>

<template>
  <nav class="fixed bottom-0 z-40 flex w-full justify-around border-t border-slate-200/80 bg-white/80 px-2 py-2 backdrop-blur-md supports-[backdrop-filter]:bg-white/60 dark:border-slate-800/80 dark:bg-slate-950/80 dark:supports-[backdrop-filter]:bg-slate-950/60 sm:hidden">
    <RouterLink
      v-for="item in items"
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
</template>
