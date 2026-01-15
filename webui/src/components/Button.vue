<script setup lang="ts">
import { computed } from 'vue';

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md" | "lg";

const props = withDefaults(
  defineProps<{
    variant?: Variant;
    size?: Size;
    disabled?: boolean;
    loading?: boolean;
    block?: boolean;
  }>(),
  {
    variant: "secondary",
    size: "md",
    disabled: false,
    loading: false,
    block: false,
  }
);

const classes = computed(() => {
  const base = 'inline-flex items-center justify-center rounded-xl font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed';

  const variants: Record<Variant, string> = {
    // Primary: Vibrant Gradient + Soft Shadow
    primary: 'bg-gradient-to-br from-brand-500 to-brand-600 hover:to-brand-500 text-white shadow-lg shadow-brand-500/25 hover:shadow-brand-500/40 active:scale-[0.98] border border-transparent ring-offset-white dark:ring-offset-slate-900',

    // Secondary: Clean White/Dark + Subtle Border
    secondary: 'bg-white text-slate-700 hover:bg-slate-50 hover:text-slate-900 border border-slate-200 shadow-sm hover:shadow active:scale-[0.98] dark:bg-slate-800 dark:text-slate-200 dark:border-slate-700 dark:hover:bg-slate-750 ring-offset-white dark:ring-offset-slate-900',

    // Danger: Rose Gradient
    danger: 'bg-gradient-to-br from-rose-500 to-rose-600 hover:to-rose-500 text-white shadow-lg shadow-rose-500/25 hover:shadow-rose-500/40 active:scale-[0.98] border border-transparent ring-offset-white dark:ring-offset-slate-900',

    // Ghost: Minimalist
    ghost: 'bg-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900 active:scale-[0.98] dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-slate-200 ring-offset-white dark:ring-offset-slate-900',
  };

  const sizes: Record<Size, string> = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-5 py-2.5 text-sm',
    lg: 'px-6 py-3 text-base',
  };

  return [
    base,
    variants[props.variant],
    sizes[props.size],
    props.block ? 'w-full' : '',
    props.loading ? 'cursor-wait' : '',
  ].join(' ');
});
</script>

<template>
  <button :class="classes" :disabled="disabled || loading">
    <svg v-if="loading" class="mr-2 -ml-1 h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none"
      viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z">
      </path>
    </svg>
    <slot />
  </button>
</template>
