<script setup lang="ts">
type Padding = "none" | "sm" | "md";

const props = withDefaults(
  defineProps<{
    title?: string;
    padding?: Padding;
    hoverable?: boolean;
  }>(),
  {
    padding: "md",
    hoverable: true,
  }
);

const paddingClass: Record<Padding, string> = {
  none: "p-0",
  sm: "p-4",
  md: "p-5",
};
</script>

<template>
  <div
    class="relative rounded-2xl border-2 border-slate-200 bg-white text-slate-900 shadow-[6px_6px_0_0_rgba(15,23,42,0.08)] transition-[transform,box-shadow] duration-150 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:shadow-[6px_6px_0_0_rgba(0,0,0,0.35)]"
    :class="
      [
        paddingClass[props.padding],
        props.hoverable
          ? 'hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[8px_8px_0_0_rgba(15,23,42,0.10)] dark:hover:shadow-[8px_8px_0_0_rgba(0,0,0,0.42)]'
          : '',
      ].join(' ')
    "
  >
    <div v-if="props.title" class="mb-4 text-sm font-semibold">
      {{ props.title }}
    </div>
    <slot />
  </div>
</template>
