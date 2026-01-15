<script setup lang="ts">
type Variant = "primary" | "secondary" | "danger" | "ghost";

const props = withDefaults(
  defineProps<{
    variant?: Variant;
    disabled?: boolean;
    loading?: boolean;
  }>(),
  {
    variant: "secondary",
    disabled: false,
    loading: false,
  }
);

const variantClasses: Record<Variant, string> = {
  primary:
    "border-2 border-slate-900 bg-brand-500 text-white shadow-[3px_3px_0_0_rgba(15,23,42,0.20)] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 active:translate-x-0 active:translate-y-0 dark:border-slate-100/40 dark:shadow-[3px_3px_0_0_rgba(0,0,0,0.35)]",
  secondary:
    "border-2 border-slate-200 bg-white text-slate-900 shadow-[3px_3px_0_0_rgba(15,23,42,0.08)] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 active:translate-x-0 active:translate-y-0 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:shadow-[3px_3px_0_0_rgba(0,0,0,0.35)]",
  danger:
    "border-2 border-danger-200 bg-danger-50 text-danger-900 shadow-[3px_3px_0_0_rgba(244,63,94,0.12)] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 active:translate-x-0 active:translate-y-0 dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-100 dark:shadow-[3px_3px_0_0_rgba(0,0,0,0.35)]",
  ghost:
    "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200",
};
</script>

<template>
  <button
    class="inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-500/25 dark:focus-visible:ring-brand-400/25"
    :class="variantClasses[props.variant]"
    :disabled="props.disabled || props.loading"
  >
    <svg
      v-if="props.loading"
      class="h-4 w-4 animate-spin"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        class="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        stroke-width="4"
      />
      <path
        class="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
    <slot />
  </button>
</template>
