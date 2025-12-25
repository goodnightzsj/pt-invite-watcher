<script setup lang="ts">
type Tone = "green" | "red" | "amber" | "slate";

const props = defineProps<{
  label: string;
  tone?: Tone;
}>();

const toneClasses: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:ring-emerald-900/70",
  red: "bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-950/40 dark:text-rose-200 dark:ring-rose-900/70",
  amber: "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-900/70",
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

