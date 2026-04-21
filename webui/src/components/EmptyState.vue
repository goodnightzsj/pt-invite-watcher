<script setup lang="ts">
import Button from "./Button.vue";
import { Inbox } from "lucide-vue-next";

defineProps<{
  title?: string;
  description?: string;
  actionText?: string;
}>();

defineEmits<{
  (e: "action"): void;
}>();
</script>

<template>
  <div class="flex flex-col items-center justify-center p-12 text-center text-slate-500 dark:text-slate-300">
    <div
      class="mb-5 flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-brand-50 to-slate-50 shadow-inner ring-1 ring-slate-200/60 dark:from-brand-950/40 dark:to-slate-900/60 dark:ring-white/5"
    >
      <slot name="icon">
        <!-- Default Icon: Inbox -->
        <Inbox class="size-9 text-slate-400/80 dark:text-slate-400" />
      </slot>
    </div>
    <h3 v-if="title" class="text-lg font-semibold text-slate-900 dark:text-white">{{ title }}</h3>
    <p v-if="description" class="mt-1.5 max-w-sm text-sm leading-relaxed opacity-80">{{ description }}</p>
    <div v-if="actionText" class="mt-6">
      <Button variant="primary" @click="$emit('action')">{{ actionText }}</Button>
    </div>
  </div>
</template>
