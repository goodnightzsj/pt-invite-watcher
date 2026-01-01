<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<template>
  <div
    class="rounded-3xl border border-slate-200/60 bg-white p-6 shadow-sm shadow-slate-200/50 transition-shadow hover:shadow-md dark:border-slate-800/60 dark:bg-slate-900/50 dark:shadow-none"
  >
    <div class="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div class="flex items-center gap-2">
          <div class="h-2 w-2 rounded-full bg-brand-500 ring-2 ring-brand-100 dark:ring-brand-900"></div>
          <h2 class="text-lg font-bold text-slate-900 dark:text-white">{{ title }}</h2>
        </div>
        <p v-if="description" class="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {{ description }}
        </p>
        <slot v-else name="description" />
      </div>
      <div class="flex flex-wrap items-center gap-4">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>
