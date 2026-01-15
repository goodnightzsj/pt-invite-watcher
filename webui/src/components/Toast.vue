<script setup lang="ts">
import { computed } from "vue";
import { AlertTriangle, CheckCircle2, Info } from "lucide-vue-next";
import type { ToastKind } from "../toast";

const props = defineProps<{
  kind: ToastKind;
  message?: string;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

const view = computed(() => {
  if (props.kind === "success") {
    return {
      box: "border-success-200 bg-success-50 text-success-900 shadow-[6px_6px_0_0_rgba(16,185,129,0.16)] dark:border-success-900 dark:bg-success-950/40 dark:text-success-100 dark:shadow-[6px_6px_0_0_rgba(0,0,0,0.45)]",
      iconWrap: "border-success-200 bg-success-500 text-white dark:border-success-900",
      icon: "success",
    } as const;
  }
  if (props.kind === "error") {
    return {
      box: "border-danger-200 bg-danger-50 text-danger-900 shadow-[6px_6px_0_0_rgba(244,63,94,0.16)] dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-100 dark:shadow-[6px_6px_0_0_rgba(0,0,0,0.45)]",
      iconWrap: "border-danger-200 bg-danger-500 text-white dark:border-danger-900",
      icon: "error",
    } as const;
  }
  return {
    box: "border-slate-200 bg-white text-slate-900 shadow-[6px_6px_0_0_rgba(15,23,42,0.08)] dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:shadow-[6px_6px_0_0_rgba(0,0,0,0.45)]",
    iconWrap: "border-slate-200 bg-slate-900 text-white dark:border-slate-800 dark:bg-slate-100 dark:text-slate-900",
    icon: "info",
  } as const;
});
</script>

<template>
  <div
    class="max-w-sm cursor-pointer rounded-2xl border-2 px-4 py-3 text-sm font-medium transition-transform duration-150 hover:-translate-x-0.5 hover:-translate-y-0.5 active:translate-x-0 active:translate-y-0"
    :class="view.box"
    @click="emit('close')"
    role="alert"
  >
    <div class="flex items-start gap-3">
      <div
        class="mt-0.5 flex h-9 w-9 items-center justify-center rounded-xl border-2 shadow-[3px_3px_0_0_rgba(15,23,42,0.08)] dark:shadow-[3px_3px_0_0_rgba(0,0,0,0.35)]"
        :class="view.iconWrap"
        aria-hidden="true"
      >
        <CheckCircle2 v-if="view.icon === 'success'" class="h-5 w-5" />
        <AlertTriangle v-else-if="view.icon === 'error'" class="h-5 w-5" />
        <Info v-else class="h-5 w-5" />
      </div>
      <div class="min-w-0 flex-1 leading-snug">
        <slot>{{ message }}</slot>
      </div>
    </div>
  </div>
</template>
