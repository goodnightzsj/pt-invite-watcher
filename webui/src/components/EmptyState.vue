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
  <div class="flex flex-col items-center justify-center p-12 text-center text-slate-500 dark:text-slate-400">
    <div class="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-50 shadow-inner dark:bg-slate-800/50">
      <slot name="icon">
        <!-- Default Icon: Inbox -->
        <Inbox class="size-8 text-slate-400/80" />
      </slot>
    </div>
    <h3 v-if="title" class="text-base font-semibold text-slate-900 dark:text-white">{{ title }}</h3>
    <p v-if="description" class="mt-1 max-w-sm text-sm opacity-80">{{ description }}</p>
    <div v-if="actionText" class="mt-6">
      <Button variant="primary" @click="$emit('action')">{{ actionText }}</Button>
    </div>
  </div>
</template>
