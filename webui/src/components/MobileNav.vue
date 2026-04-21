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
  <nav class="fixed bottom-0 z-40 flex w-full justify-around border-t border-white/20 bg-white/80 pb-safe pt-2 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/80 md:hidden">
    <RouterLink
      v-for="item in items"
      :key="item.to"
      :to="item.to"
      class="group flex flex-1 flex-col items-center justify-center gap-1 rounded-xl py-2 text-[10px] font-medium transition-all active:scale-95"
      :class="
        isActive(item.to)
          ? 'text-brand-600 dark:text-brand-400'
          : 'text-slate-500 hover:text-slate-700 dark:text-slate-300 dark:hover:text-slate-200'
      "
    >
      <div 
        class="relative flex h-8 w-12 items-center justify-center rounded-full transition-colors"
        :class="isActive(item.to) ? 'bg-brand-50/80 dark:bg-brand-500/10' : 'bg-transparent group-hover:bg-slate-100 dark:group-hover:bg-white/5'"
      >
        <component :is="item.icon" class="h-5 w-5" :stroke-width="isActive(item.to) ? 2.5 : 2" />
      </div>
      <span>{{ item.label }}</span>
    </RouterLink>
  </nav>
</template>
