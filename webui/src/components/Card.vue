<script setup lang="ts">
type Padding = "none" | "sm" | "md" | "lg";

const props = withDefaults(
  defineProps<{
    title?: string;
    padding?: Padding;
    hoverable?: boolean;
    noHover?: boolean; // Backwards compat or new alias
  }>(),
  {
    padding: "md",
    hoverable: true,
  }
);

const paddingClass: Record<Padding, string> = {
  none: "p-0",
  sm: "p-4",
  md: "p-6",
  lg: "p-8",
};
</script>

<template>
  <div
    class="relative glass rounded-2xl border-0 bg-white/5 shadow-xl backdrop-blur-md transition-all duration-300 dark:bg-slate-900/40 dark:border-white/5"
    :class="
      [
        paddingClass[props.padding],
        (props.hoverable && !props.noHover)
          ? 'hover:-translate-y-1 hover:shadow-cyan-500/20 hover:border-white/20'
          : '',
      ].join(' ')
    "
  >
    <div v-if="props.title" class="mb-4 text-sm font-semibold tracking-tight text-slate-800 dark:text-slate-200">
      {{ props.title }}
    </div>
    <slot />
  </div>
</template>
