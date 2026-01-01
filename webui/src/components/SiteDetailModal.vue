<script setup lang="ts">
import { computed } from "vue";
import type { SiteRow } from "../api";
import Modal from "./Modal.vue";
import Badge from "./Badge.vue";

const props = defineProps<{
  open: boolean;
  site: SiteRow | null;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

const siteName = computed(() => {
  if (!props.site) return "";
  return props.site.name || props.site.domain;
});
</script>

<template>
  <Modal :open="open" :title="siteName" @close="emit('close')">
    <div v-if="site" class="space-y-6">
      
      <!-- Top Meta -->
      <div class="flex flex-col gap-4 sm:flex-row sm:justify-between">
        <div class="space-y-1">
          <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">基本信息</div>
          <div class="flex items-center gap-2">
             <a :href="site.url" target="_blank" class="text-sm text-brand-600 hover:underline dark:text-brand-400">
               {{ site.url }}
             </a>
          </div>
          <div class="text-xs text-slate-500">引擎: {{ site.engine }}</div>
        </div>
        
        <div class="flex flex-wrap gap-2">
            <Badge label="连通性" :tone="site.reachability_state === 'up' ? 'green' : site.reachability_state === 'down' ? 'red' : 'slate'" />
            <Badge label="注册" :tone="site.registration_state === 'open' ? 'green' : site.registration_state === 'closed' ? 'amber' : 'slate'" />
            <Badge label="邀请" :tone="site.invites_state === 'open' ? 'brand' : site.invites_state === 'closed' ? 'slate' : 'slate'" />
        </div>
      </div>

      <!-- Dates -->
      <div class="grid grid-cols-2 gap-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/50">
           <div>
             <div class="text-xs text-slate-500 dark:text-slate-400">上次检查</div>
             <div class="font-mono text-sm">{{ site.last_checked_at.replace('T', ' ').split('.')[0] || '-' }}</div>
           </div>
           <div>
             <div class="text-xs text-slate-500 dark:text-slate-400">状态变更</div>
             <div class="font-mono text-sm">{{ site.last_changed_at?.replace('T', ' ').split('.')[0] || '-' }}</div>
           </div>
      </div>

      <!-- Errors Section -->
      <div v-if="site.errors && site.errors.length > 0">
        <div class="mb-2 text-sm font-semibold text-danger-700 dark:text-danger-400">错误日志 (当前)</div>
        <div class="max-h-60 overflow-y-auto rounded-xl border border-danger-200 bg-danger-50 p-3 text-xs font-mono text-danger-900 dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-200">
          <div v-for="(err, idx) in site.errors" :key="idx" class="mb-1 border-b border-danger-200/50 pb-1 last:border-0 last:pb-0">
            {{ err }}
          </div>
        </div>
      </div>
      
      <!-- Notes -->
      <div v-if="site.reachability_note || site.registration_note" class="space-y-2">
          <div v-if="site.reachability_note" class="text-xs">
            <span class="font-bold">连通性备注:</span> {{ site.reachability_note }}
          </div>
          <div v-if="site.registration_note" class="text-xs">
            <span class="font-bold">注册备注:</span> {{ site.registration_note }}
          </div>
      </div>

    </div>
  </Modal>
</template>
