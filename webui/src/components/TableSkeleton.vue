<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    rows?: number;
    cols?: number;
  }>(),
  {
    rows: 5,
    cols: 7,
  }
);
</script>

<template>
  <div class="animate-pulse">
    <table class="min-w-full text-left text-sm">
      <thead class="border-b border-slate-200/70 bg-slate-50 text-xs uppercase tracking-wider text-slate-500 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-400">
        <tr>
          <th v-for="c in props.cols" :key="c" class="px-6 py-4">
            <div class="h-3 w-16 rounded bg-slate-200 dark:bg-slate-700" />
          </th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-100 dark:divide-slate-800/60">
        <tr v-for="r in props.rows" :key="r">
          <td v-for="c in props.cols" :key="c" class="px-6 py-4">
            <div
              class="h-4 rounded bg-slate-200 dark:bg-slate-700"
              :class="c === 1 ? 'w-32' : c === props.cols ? 'w-12' : 'w-20'"
            />
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
