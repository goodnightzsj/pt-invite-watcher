<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref } from "vue";
import { Check, ChevronDown } from "lucide-vue-next";

export type SelectValue = string | number;

export type SelectOption = {
  label: string;
  value: SelectValue;
  disabled?: boolean;
  help?: string;
};

const props = withDefaults(
  defineProps<{
    label?: string;
    modelValue?: SelectValue | null;
    options: SelectOption[];
    placeholder?: string;
    disabled?: boolean;
    dense?: boolean;
  }>(),
  {
    placeholder: "请选择",
    disabled: false,
    modelValue: null,
    dense: false,
  }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: SelectValue): void;
}>();

const open = ref(false);
const triggerRef = ref<HTMLElement | null>(null);
const panelRef = ref<HTMLElement | null>(null);
const panelStyle = ref<Record<string, string>>({});

const selected = computed(() => props.options.find((o) => o.value === props.modelValue) || null);

function closePicker() {
  if (!open.value) return;
  open.value = false;
  teardownGlobalListeners();
}

function updatePosition() {
  const el = triggerRef.value;
  if (!el) return;

  const rect = el.getBoundingClientRect();
  const margin = 8;
  const width = rect.width;
  const maxHeight = Math.min(320, Math.max(160, window.innerHeight - margin * 2));

  let left = rect.left;
  const maxLeft = window.innerWidth - margin - width;
  if (left > maxLeft) left = Math.max(margin, maxLeft);

  const preferBelow = rect.bottom + margin;
  const preferAbove = rect.top - margin - maxHeight;
  const shouldPlaceAbove = preferBelow + maxHeight > window.innerHeight - margin && preferAbove >= margin;

  const top = shouldPlaceAbove ? rect.top - margin - maxHeight : preferBelow;

  panelStyle.value = {
    position: "fixed",
    left: `${Math.round(left)}px`,
    top: `${Math.round(top)}px`,
    width: `${Math.round(width)}px`,
    maxHeight: `${Math.round(maxHeight)}px`,
    zIndex: "60",
  };
}

function onPointerDown(e: PointerEvent) {
  const target = e.target as Node | null;
  if (!target) return;
  if (triggerRef.value?.contains(target)) return;
  if (panelRef.value?.contains(target)) return;
  closePicker();
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === "Escape") closePicker();
}

function onViewportChange() {
  if (!open.value) return;
  updatePosition();
}

function setupGlobalListeners() {
  document.addEventListener("pointerdown", onPointerDown, true);
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("resize", onViewportChange);
  window.addEventListener("scroll", onViewportChange, true);
}

function teardownGlobalListeners() {
  document.removeEventListener("pointerdown", onPointerDown, true);
  window.removeEventListener("keydown", onKeyDown);
  window.removeEventListener("resize", onViewportChange);
  window.removeEventListener("scroll", onViewportChange, true);
}

async function openPicker() {
  if (props.disabled) return;
  open.value = true;
  setupGlobalListeners();
  await nextTick();
  updatePosition();
}

function pick(value: SelectValue) {
  emit("update:modelValue", value);
  closePicker();
}

onUnmounted(() => teardownGlobalListeners());
</script>

<template>
  <div>
    <label v-if="props.label" class="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-200">
      {{ props.label }}
    </label>

    <button
      ref="triggerRef"
      type="button"
      class="ui-input flex w-full items-center justify-between gap-2 text-left disabled:cursor-not-allowed disabled:opacity-60"
      :class="props.dense ? '!rounded-lg !px-2 !py-1.5 !text-sm' : ''"
      :disabled="props.disabled"
      @click="openPicker"
      aria-haspopup="listbox"
      :aria-expanded="open ? 'true' : 'false'"
    >
      <span
        class="min-w-0 flex-1 truncate"
        :class="selected ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'"
      >
        {{ selected ? selected.label : props.placeholder }}
      </span>
      <ChevronDown class="h-4 w-4 text-slate-500 dark:text-slate-400" aria-hidden="true" />
    </button>

    <slot name="help" />

    <teleport to="body">
      <transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="opacity-0 -translate-y-1 scale-95"
        enter-to-class="opacity-100 translate-y-0 scale-100"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="opacity-100 translate-y-0 scale-100"
        leave-to-class="opacity-0 -translate-y-1 scale-95"
      >
        <div
          v-if="open"
          ref="panelRef"
          class="overflow-hidden rounded-xl border border-slate-200/60 bg-white/95 shadow-xl backdrop-blur-md dark:border-slate-700/60 dark:bg-slate-900/95"
          :style="panelStyle"
          role="listbox"
        >
          <div class="max-h-[inherit] overflow-auto divide-y divide-slate-100 dark:divide-slate-800/60">
            <button
              v-for="opt in props.options"
              :key="String(opt.value)"
              type="button"
              class="flex w-full items-start justify-between gap-3 px-4 py-3 text-left text-sm transition-colors hover:bg-slate-50 active:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 dark:hover:bg-slate-900 dark:active:bg-slate-800"
              :disabled="!!opt.disabled"
              @click="pick(opt.value)"
            >
              <div class="min-w-0 flex-1">
                <div class="font-medium text-slate-900 dark:text-slate-100">{{ opt.label }}</div>
                <div v-if="opt.help" class="mt-0.5 text-xs text-slate-600 dark:text-slate-400">{{ opt.help }}</div>
              </div>
              <Check
                v-if="opt.value === props.modelValue"
                class="mt-0.5 h-5 w-5 shrink-0 text-brand-600 dark:text-brand-400"
                aria-hidden="true"
              />
            </button>
          </div>
        </div>
      </transition>
    </teleport>
  </div>
</template>
