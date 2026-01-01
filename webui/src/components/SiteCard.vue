<script setup lang="ts">
import { computed } from "vue";
import type { SiteRow } from "../api";
import Badge from "./Badge.vue";
import SiteIcon from "./SiteIcon.vue";
import { ChevronRight } from "lucide-vue-next";
import { formatRelativeTime } from "../utils/date";

const props = defineProps<{
  site: SiteRow;
}>();

const emit = defineEmits<{
  (e: "click"): void;
}>();



// Using the same reachability badge logic as table
const reachability = computed(() => {
  if (props.site.reachability_state === "up") return { label: "连通", tone: "green" };
  if (props.site.reachability_state === "down") return { label: "无法访问", tone: "red" };
  return { label: "未知", tone: "slate" };
});

const regState = computed(() => {
  if (props.site.registration_state === 'open') return { label: '开放注册', tone: 'green' };
  if (props.site.registration_state === 'closed') return { label: '关闭注册', tone: 'amber' };
  return { label: '未知', tone: 'slate' };
});

const inviteState = computed(() => {
  if (props.site.invites_state === 'open') return { label: '开放邀请', tone: 'brand' };
  if (props.site.invites_state === 'closed') return { label: '关闭邀请', tone: 'red' };
  return { label: '邀请未知', tone: 'amber' };
});

</script>

<template>
  <div
    class="relative overflow-hidden rounded-xl bg-white p-4 shadow-sm transition-all active:scale-[0.98] dark:bg-slate-900/50 glass hover:shadow-md hover:ring-2 hover:ring-brand-500/20"
    @click="emit('click')">
    <div class="flex items-start justify-between">
      <!-- Left: Icon & Name -->
      <div class="flex items-center gap-3">
        <div class="h-10 w-10">
          <SiteIcon :url="site.url" :name="site.name || site.domain" />
        </div>
        <div>
          <div class="font-semibold text-slate-800 dark:text-slate-100">{{ site.name || site.domain }}</div>
          <div class="text-xs text-slate-400">{{ site.domain }}</div>
        </div>
      </div>

      <!-- Right: Action Arrow -->
      <ChevronRight class="h-5 w-5 text-slate-300 dark:text-slate-600" />
    </div>

    <!-- Middle: Status Badges -->
    <div class="mt-4 flex flex-wrap gap-2">
      <Badge :label="reachability.label" :tone="reachability.tone as any" />
      <Badge :label="regState.label" :tone="regState.tone as any" />
      <Badge :label="inviteState.label" :tone="inviteState.tone as any" />
    </div>

    <!-- Footer: Time -->
    <div
      class="mt-3 flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-400 dark:border-slate-800">
      <div>{{ site.engine }}</div>
      <div>{{ formatRelativeTime(site.last_checked_at) }} 更新</div>
    </div>

  </div>
</template>
