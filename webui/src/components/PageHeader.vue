<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<template>
  <div class="mb-8">
    <div class="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
      <div class="relative">
        <!-- Breathing Status Beam -->
        <div
          class="pointer-events-none absolute -left-4 top-1 h-8 w-1 rounded-full bg-gradient-to-b from-brand-400 to-transparent opacity-0 transition-opacity duration-500 sm:opacity-100">
        </div>

        <div class="flex items-center gap-3">
          <h2
            class="text-3xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-slate-900 to-slate-600 dark:from-white dark:to-slate-300">
            {{ title }}
          </h2>
        </div>
        <p v-if="description"
          class="mt-2 text-base font-medium text-slate-500 dark:text-slate-400 max-w-2xl leading-relaxed">
          {{ description }}
        </p>
        <slot v-else name="description" />
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <slot name="actions" />
      </div>
    </div>

    <!-- Optional: Subtle divider if needed, but clean is better -->
    <!-- <div class="mt-8 h-px w-full bg-gradient-to-r from-slate-200/50 via-slate-200 to-transparent dark:from-white/5 dark:via-white/10"></div> -->
  </div>
</template>
