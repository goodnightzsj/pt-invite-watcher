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
    <transition name="modal-backdrop">
      <div
        v-if="props.open"
        class="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
        @click="emit('close')"
        aria-label="Close modal"
      />
    </transition>
    <transition name="modal-content">
      <div
        v-if="props.open"
        class="fixed inset-0 z-50 flex items-center justify-center px-4 pointer-events-none"
      >
        <div
          class="pointer-events-auto relative w-full max-w-2xl overflow-hidden rounded-2xl glass border-slate-200 bg-white/80 shadow-2xl dark:border-slate-800 dark:bg-slate-900/80 sm:rounded-2xl max-sm:rounded-t-2xl max-sm:rounded-b-none max-sm:fixed max-sm:bottom-0 max-sm:left-0 max-sm:right-0 max-sm:max-h-[85vh]"
        >
          <div class="flex items-center justify-between border-b border-slate-200/50 px-5 py-4 dark:border-slate-700/50">
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
    </transition>
  </teleport>
</template>

<style scoped>
/* Backdrop fade */
.modal-backdrop-enter-active,
.modal-backdrop-leave-active {
  transition: opacity 0.2s ease;
}
.modal-backdrop-enter-from,
.modal-backdrop-leave-to {
  opacity: 0;
}

/* Content scale + fade */
.modal-content-enter-active,
.modal-content-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.modal-content-enter-from {
  opacity: 0;
  transform: scale(0.95);
}
.modal-content-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
</style>

