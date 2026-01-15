<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<template>
  <div
    class="rounded-3xl border-2 border-slate-200 bg-white text-slate-900 shadow-[8px_8px_0_0_rgba(15,23,42,0.08)] dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:shadow-[8px_8px_0_0_rgba(0,0,0,0.35)]"
  >
    <div class="flex flex-col gap-6 p-6 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div class="flex items-center gap-2">
          <div class="h-2 w-2 rounded-full bg-brand-500 ring-2 ring-brand-100 dark:ring-brand-900"></div>
          <h2 class="text-lg font-bold">{{ title }}</h2>
        </div>
        <p v-if="description" class="mt-1 text-sm text-slate-600 dark:text-slate-400">
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
