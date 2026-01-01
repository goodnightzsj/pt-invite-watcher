<script setup lang="ts">
type Tone = "green" | "red" | "amber" | "slate";

const props = defineProps<{
  label: string;
  tone?: Tone;
}>();

const toneClasses: Record<Tone, string> = {
  green: "bg-success-50 text-success-700 ring-success-200 dark:bg-success-950/40 dark:text-success-200 dark:ring-success-900/70",
  red: "bg-danger-50 text-danger-700 ring-danger-200 dark:bg-danger-950/40 dark:text-danger-200 dark:ring-danger-900/70",
  amber: "bg-warning-50 text-warning-700 ring-warning-200 dark:bg-warning-950/40 dark:text-warning-200 dark:ring-warning-900/70",
  slate: "bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-900/60 dark:text-slate-200 dark:ring-slate-800",
};
</script>

<template>
  <span
    class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset"
    :class="toneClasses[props.tone || 'slate']"
  >
    {{ props.label }}
  </span>
</template>

