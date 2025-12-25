<script setup lang="ts">
const props = defineProps<{
  modelValue: boolean;
  label?: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
}>();
</script>

<template>
  <label class="inline-flex items-center gap-2">
    <button
      type="button"
      class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
      :class="props.modelValue ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700'"
      @click="emit('update:modelValue', !props.modelValue)"
      aria-label="toggle"
    >
      <span
        class="inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform"
        :class="props.modelValue ? 'translate-x-5' : 'translate-x-1'"
      />
    </button>
    <span v-if="props.label" class="text-sm text-slate-700 dark:text-slate-200">{{ props.label }}</span>
  </label>
</template>

