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
    "bg-gradient-to-r from-brand-600 to-brand-500 text-white shadow-lg shadow-brand-500/20 hover:translate-y-[-1px] hover:shadow-brand-500/30 dark:shadow-none",
  secondary:
    "border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 hover:text-slate-900 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white",
  danger:
    "border border-danger-200 bg-danger-50 text-danger-800 shadow-sm hover:bg-danger-100 dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-200 dark:hover:bg-danger-950/60",
  ghost:
    "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200",
};
</script>

<template>
  <button
    class="inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-60"
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
