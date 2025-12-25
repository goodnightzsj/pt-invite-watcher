<script setup lang="ts">
const props = defineProps<{
  open: boolean;
  title: string;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();
</script>

<template>
  <teleport to="body">
    <div v-if="props.open" class="fixed inset-0 z-50 flex items-center justify-center px-4">
      <button class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="emit('close')" aria-label="Close modal" />
      <div
        class="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div class="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800">
          <div class="text-base font-semibold">{{ props.title }}</div>
          <button
            class="rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            @click="emit('close')"
          >
            关闭
          </button>
        </div>
        <div class="max-h-[70vh] overflow-auto px-5 py-4">
          <slot />
        </div>
      </div>
    </div>
  </teleport>
</template>

