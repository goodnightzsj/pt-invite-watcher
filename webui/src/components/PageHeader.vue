<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<template>
  <div class="mb-8">
    <div class="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h2 class="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
          {{ title }}
        </h2>
        <p
          v-if="description"
          class="mt-2 max-w-2xl text-base leading-relaxed text-slate-600 dark:text-slate-300"
        >
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
