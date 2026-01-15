<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import { X } from "lucide-vue-next";

const props = defineProps<{
  open: boolean;
  title: string;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

function onKeydown(e: KeyboardEvent) {
  if (props.open && e.key === "Escape") {
    emit("close");
  }
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <teleport to="body">
    <transition name="modal-backdrop">
      <div
        v-if="props.open"
        class="fixed inset-0 z-50 bg-black/55"
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
          class="pointer-events-auto relative w-full max-w-2xl overflow-hidden rounded-2xl border-2 border-slate-200 bg-white shadow-[12px_12px_0_0_rgba(15,23,42,0.10)] dark:border-slate-800 dark:bg-slate-950 dark:shadow-[12px_12px_0_0_rgba(0,0,0,0.45)] max-sm:rounded-t-2xl max-sm:rounded-b-none max-sm:fixed max-sm:bottom-0 max-sm:left-0 max-sm:right-0 max-sm:max-h-[85vh]"
        >
          <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
            <div class="text-base font-semibold text-slate-900 dark:text-slate-100">{{ props.title }}</div>
            <button
              class="rounded-xl border-2 border-slate-200 bg-white px-2 py-1.5 text-slate-600 shadow-[3px_3px_0_0_rgba(15,23,42,0.08)] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 active:translate-x-0 active:translate-y-0 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300 dark:shadow-[3px_3px_0_0_rgba(0,0,0,0.35)]"
              @click="emit('close')"
              title="Close (Esc)"
            >
              <X class="h-5 w-5" />
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
