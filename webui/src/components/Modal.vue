<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { X } from "lucide-vue-next";

const props = defineProps<{
  open: boolean;
  title: string;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

const dialogRef = ref<HTMLElement | null>(null);
let lastFocused: HTMLElement | null = null;

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function focusableElements(): HTMLElement[] {
  if (!dialogRef.value) return [];
  return Array.from(dialogRef.value.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
    .filter((el) => !el.hasAttribute("disabled") && el.offsetParent !== null);
}

function onKeydown(e: KeyboardEvent) {
  if (!props.open) return;
  if (e.key === "Escape") {
    e.stopPropagation();
    emit("close");
    return;
  }
  if (e.key !== "Tab") return;
  // Trap focus inside the dialog.
  const els = focusableElements();
  if (els.length === 0) {
    e.preventDefault();
    return;
  }
  const first = els[0];
  const last = els[els.length - 1];
  const active = document.activeElement as HTMLElement | null;
  if (e.shiftKey) {
    if (active === first || !dialogRef.value?.contains(active)) {
      e.preventDefault();
      last.focus();
    }
  } else {
    if (active === last) {
      e.preventDefault();
      first.focus();
    }
  }
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      lastFocused = document.activeElement as HTMLElement | null;
      await nextTick();
      const els = focusableElements();
      (els[0] || dialogRef.value)?.focus();
    } else if (lastFocused && typeof lastFocused.focus === "function") {
      lastFocused.focus();
      lastFocused = null;
    }
  }
);

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <teleport to="body">
    <transition name="modal-backdrop">
      <div v-if="props.open" class="fixed inset-0 z-50 bg-black/55" @click="emit('close')" aria-label="Close modal" />
    </transition>
    <transition name="modal-content">
      <div v-if="props.open" class="fixed inset-0 z-50 flex items-center justify-center px-4 pointer-events-none">
        <div
          ref="dialogRef"
          role="dialog"
          aria-modal="true"
          :aria-label="props.title"
          tabindex="-1"
          class="pointer-events-auto relative w-full max-w-2xl overflow-hidden rounded-2xl border border-white/40 bg-white/80 shadow-2xl shadow-brand-500/10 backdrop-blur-2xl outline-none dark:border-white/10 dark:bg-slate-900/80 max-sm:rounded-t-2xl max-sm:rounded-b-none max-sm:fixed max-sm:bottom-0 max-sm:left-0 max-sm:right-0 max-sm:max-h-[85vh] transition-all">
          <div class="flex items-center justify-between border-b border-slate-200/50 px-5 py-4 dark:border-white/5">
            <div class="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">{{ props.title }}</div>
            <button
              class="rounded-xl p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
              @click="emit('close')" title="Close (Esc)" aria-label="Close">
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
