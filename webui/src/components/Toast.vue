<script setup lang="ts">
import { computed } from "vue";
import type { ToastKind } from "../toast";

const props = defineProps<{
  kind: ToastKind;
  message?: string;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

const classes = computed(() => {
  if (props.kind === "success") {
    return "border-success-200 bg-success-50 text-success-800 dark:border-success-900 dark:bg-success-950/40 dark:text-success-200";
  } else if (props.kind === "error") {
    return "border-danger-200 bg-danger-50 text-danger-800 dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-200";
  }
  return "border-slate-200 bg-white text-slate-800 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100";
});
</script>

<template>
  <div
    class="max-w-sm cursor-pointer rounded-2xl border px-4 py-3 text-sm shadow-lg backdrop-blur-sm transition-all hover:opacity-90 active:scale-95"
    :class="classes"
    @click="emit('close')"
    role="alert"
  >
    <slot>{{ message }}</slot>
  </div>
</template>
