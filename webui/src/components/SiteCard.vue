<script setup lang="ts">
import { computed } from "vue";
import type { SiteRow } from "../api";
import Badge from "./Badge.vue";
import SiteIcon from "./SiteIcon.vue";
import { ChevronRight } from "lucide-vue-next";
import RelativeTime from "./RelativeTime.vue";

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
    class="group relative overflow-hidden rounded-2xl border border-white/20 bg-white/5 p-5 shadow-md backdrop-blur-md transition-shadow duration-200 hover:shadow-lg hover:shadow-brand-500/10 active:scale-[0.99] dark:border-white/10 dark:bg-slate-900/40"
    :class="site.scanning ? 'row-scanning' : ''"
    @click="emit('click')"
  >
      <div class="flex items-start justify-between">
        <!-- Left: Icon & Name -->
        <div class="flex items-center gap-3">
          <div class="h-10 w-10">
            <SiteIcon :url="site.url" :name="site.name || site.domain" :reachability="site.reachability_state" />
          </div>
          <div>
            <div class="font-semibold text-slate-900 dark:text-slate-100">{{ site.name || site.domain }}</div>
            <div class="text-xs text-slate-500 dark:text-slate-300">{{ site.domain }}</div>
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
        class="mt-3 flex items-center justify-between border-t border-slate-200 pt-3 text-xs text-slate-600 dark:border-slate-800 dark:text-slate-300"
      >
        <div>{{ site.engine }}</div>
        <div><RelativeTime :ts="site.last_checked_at" /> 更新</div>
      </div>
  </div>
</template>
