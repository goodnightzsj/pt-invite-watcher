<script setup lang="ts">
const props = defineProps<{
  title?: string;
}>();
</script>

<template>
  <div
    class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
  >
    <div v-if="props.title" class="mb-4 text-sm font-semibold">
      {{ props.title }}
    </div>
    <slot />
  </div>
</template>
