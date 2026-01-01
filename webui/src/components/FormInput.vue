<script setup lang="ts">
defineProps<{
  label?: string;
  modelValue?: string | number;
  type?: string;
  placeholder?: string;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: string | number): void;
}>();
</script>

<template>
  <div>
    <label v-if="label" class="block text-sm font-medium mb-1 text-slate-700 dark:text-slate-200">
      {{ label }}
    </label>
    <div class="relative">
      <textarea
        v-if="type === 'textarea'"
        :value="modelValue"
        class="ui-input w-full min-h-[90px]"
        :placeholder="placeholder"
        :disabled="disabled"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
      <input
        v-else
        :value="modelValue"
        :type="type || 'text'"
        class="ui-input w-full"
        :placeholder="placeholder"
        :disabled="disabled"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
      <slot name="suffix" />
    </div>
    <slot name="help" />
  </div>
</template>
