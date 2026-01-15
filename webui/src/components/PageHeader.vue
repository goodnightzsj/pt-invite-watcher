<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<template>
  <div
    class="rounded-3xl border border-white/40 bg-white/40 shadow-sm backdrop-blur-md dark:border-white/5 dark:bg-slate-900/30"
  >
    <div class="flex flex-col gap-6 p-6 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div class="flex items-center gap-3">
          <div class="relative flex h-3 w-3">
            <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-400 opacity-75"></span>
            <span class="relative inline-flex h-3 w-3 rounded-full bg-brand-500 shadow-md shadow-brand-500/50"></span>
          </div>
          <h2 class="text-xl font-bold tracking-tight text-slate-800 dark:text-slate-100">
            {{ title }}
          </h2>
        </div>
        <p v-if="description" class="mt-2 text-sm font-medium text-slate-500 dark:text-slate-400">
          {{ description }}
        </p>
        <slot v-else name="description" />
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>
