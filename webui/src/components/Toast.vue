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
      box: "border-emerald-200/50 bg-emerald-50/80 text-emerald-900 shadow-lg shadow-emerald-500/10 backdrop-blur-md dark:border-emerald-800/30 dark:bg-emerald-950/60 dark:text-emerald-100",
      iconWrap: "bg-emerald-500 text-white shadow-sm shadow-emerald-500/20",
      icon: "success",
    } as const;
  }
  if (props.kind === "error") {
    return {
      box: "border-rose-200/50 bg-rose-50/80 text-rose-900 shadow-lg shadow-rose-500/10 backdrop-blur-md dark:border-rose-800/30 dark:bg-rose-950/60 dark:text-rose-100",
      iconWrap: "bg-rose-500 text-white shadow-sm shadow-rose-500/20",
      icon: "error",
    } as const;
  }
  return {
    box: "border-slate-200/60 bg-white/80 text-slate-900 shadow-lg shadow-slate-500/10 backdrop-blur-md ring-1 ring-slate-900/5 dark:border-slate-700/50 dark:bg-slate-900/80 dark:text-slate-100 dark:ring-white/10",
    iconWrap: "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900",
    icon: "info",
  } as const;
});
</script>

<template>
  <div
    class="pointer-events-auto max-w-sm cursor-pointer rounded-2xl border px-4 py-3 text-sm font-medium transition-all duration-300 hover:-translate-y-1 hover:shadow-xl active:scale-[0.98]"
    :class="view.box"
    @click="emit('close')"
    role="alert"
  >
    <div class="flex items-start gap-3">
      <div
        class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
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
