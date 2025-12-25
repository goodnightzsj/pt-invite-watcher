<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import Badge from "../components/Badge.vue";
import Modal from "../components/Modal.vue";
import Toggle from "../components/Toggle.vue";
import { api, type SiteRow } from "../api";
import { showToast } from "../toast";

type AutoRefreshMinutes = 1 | 5 | 10 | 30 | 60 | 120 | 360 | 720 | 1440;

const STORAGE_REFRESH_ENABLED = "ptiw_auto_refresh_enabled";
const STORAGE_REFRESH_MINUTES = "ptiw_auto_refresh_minutes";

const loading = ref(false);
const scanRunning = ref(false);
const rows = ref<SiteRow[]>([]);
const scanStatus = ref<any>(null);

const autoRefreshEnabled = ref(localStorage.getItem(STORAGE_REFRESH_ENABLED) === "1");
const autoRefreshMinutes = ref<AutoRefreshMinutes>(
  ([1, 5, 10, 30, 60, 120, 360, 720, 1440] as const).includes(Number(localStorage.getItem(STORAGE_REFRESH_MINUTES)) as any)
    ? (Number(localStorage.getItem(STORAGE_REFRESH_MINUTES)) as AutoRefreshMinutes)
    : 10
);

let timer: number | undefined;

const errorModalOpen = ref(false);
const errorModalTitle = ref("");
const errorModalErrors = ref<string[]>([]);

function toneForState(state: string) {
  if (state === "open" || state === "up") return "green";
  if (state === "closed" || state === "down") return "red";
  return "amber";
}

function labelForReachability(state: string) {
  if (state === "up") return "正常";
  if (state === "down") return "异常";
  return "未知";
}

function formatDateTime(v: string | null | undefined) {
  if (!v) return "-";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" }).format(d);
}

async function refresh() {
  loading.value = true;
  try {
    const data = await api.dashboard();
    rows.value = data.rows || [];
    scanStatus.value = data.scan_status;
  } catch (e: any) {
    showToast(String(e?.message || e || "加载失败"), "error");
  } finally {
    loading.value = false;
  }
}

async function runScan() {
  scanRunning.value = true;
  try {
    const status = await api.scanRun();
    scanStatus.value = status;
    showToast(status?.ok ? "扫描已完成" : `扫描失败：${status?.error || "unknown"}`, status?.ok ? "success" : "error");
    await refresh();
  } catch (e: any) {
    showToast(String(e?.message || e || "扫描失败"), "error");
  } finally {
    scanRunning.value = false;
  }
}

function openErrors(row: SiteRow) {
  errorModalTitle.value = `${row.name || "-"} · ${row.domain}`;
  errorModalErrors.value = row.errors || [];
  errorModalOpen.value = true;
}

function clearTimer() {
  if (timer) {
    window.clearInterval(timer);
    timer = undefined;
  }
}

function setupTimer() {
  clearTimer();
  if (!autoRefreshEnabled.value) return;
  timer = window.setInterval(() => {
    refresh();
  }, autoRefreshMinutes.value * 60 * 1000);
}

watch(autoRefreshEnabled, (v) => {
  localStorage.setItem(STORAGE_REFRESH_ENABLED, v ? "1" : "0");
  setupTimer();
});
watch(autoRefreshMinutes, (v) => {
  localStorage.setItem(STORAGE_REFRESH_MINUTES, String(v));
  setupTimer();
});

onMounted(async () => {
  await refresh();
  setupTimer();
});
onUnmounted(() => clearTimer());

const hasRows = computed(() => rows.value.length > 0);
</script>

<template>
  <div class="space-y-5">
    <div
      class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-base font-semibold">站点状态</div>
          <div class="mt-1 text-sm text-slate-500 dark:text-slate-400">只在状态变化时通知；unknown 不触发通知（默认）。</div>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <div class="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 dark:border-slate-800">
            <Toggle v-model="autoRefreshEnabled" />
            <span class="text-sm text-slate-700 dark:text-slate-200">自动刷新</span>
            <select
              v-model.number="autoRefreshMinutes"
              class="ml-2 w-auto rounded-lg border-slate-200 bg-white text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
              :disabled="!autoRefreshEnabled"
            >
              <option :value="1">1 分钟</option>
              <option :value="5">5 分钟</option>
              <option :value="10">10 分钟</option>
              <option :value="30">30 分钟</option>
              <option :value="60">60 分钟</option>
              <option :value="120">120 分钟</option>
              <option :value="360">360 分钟</option>
              <option :value="720">720 分钟</option>
              <option :value="1440">1440 分钟</option>
            </select>
          </div>
          <button
            class="inline-flex items-center justify-center rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
            :disabled="scanRunning"
            @click="runScan"
          >
            {{ scanRunning ? "扫描中…" : "立即扫描" }}
          </button>
          <button
            class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            :disabled="loading"
            @click="refresh"
          >
            {{ loading ? "刷新中…" : "刷新数据" }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="scanStatus"
      class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-base font-semibold">扫描状态</div>
          <div class="mt-1 text-sm text-slate-500 dark:text-slate-400">
            最后运行：{{ scanStatus.last_run_at || "-" }} · 站点数：{{ scanStatus.site_count || 0 }}
          </div>
        </div>
        <Badge :label="scanStatus.ok ? 'ok' : 'fail'" :tone="scanStatus.ok ? 'green' : 'red'" />
      </div>
      <div v-if="!scanStatus.ok" class="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200">
        失败：{{ scanStatus.error || "unknown" }}
        <div class="mt-1 text-rose-700/80 dark:text-rose-200/80">请检查 MoviePilot 配置与站点列表是否已启用。</div>
      </div>
    </div>

    <div
      class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div class="border-b border-slate-100 px-5 py-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        <span v-if="hasRows">共 {{ rows.length }} 个站点</span>
        <span v-else>暂无数据：请先确认 MoviePilot 已配置站点并点击“立即扫描”。</span>
      </div>

      <div class="overflow-x-auto">
        <table class="min-w-full text-left text-sm">
          <thead class="bg-slate-50 text-xs text-slate-500 dark:bg-slate-950/40 dark:text-slate-400">
            <tr>
              <th class="px-5 py-3 font-medium">站点</th>
              <th class="px-5 py-3 font-medium">域名</th>
              <th class="px-5 py-3 font-medium">引擎</th>
              <th class="px-5 py-3 font-medium">可访问</th>
              <th class="px-5 py-3 font-medium">开放注册</th>
              <th class="px-5 py-3 font-medium">可用邀请</th>
              <th class="px-5 py-3 font-medium">最后检查</th>
              <th class="px-5 py-3 font-medium">最后变更</th>
              <th class="px-5 py-3 font-medium">异常</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr v-for="row in rows" :key="row.domain" class="hover:bg-slate-50/70 dark:hover:bg-slate-950/30">
              <td class="px-5 py-4 font-medium">{{ row.name || "-" }}</td>
              <td class="px-5 py-4">
                <a class="text-slate-900 underline decoration-slate-300 underline-offset-4 hover:decoration-slate-700 dark:text-slate-100 dark:decoration-slate-700 dark:hover:decoration-slate-300" :href="row.url" target="_blank" rel="noreferrer">
                  {{ row.domain }}
                </a>
              </td>
              <td class="px-5 py-4">
                <Badge :label="row.engine || 'unknown'" tone="slate" />
              </td>
              <td class="px-5 py-4">
                <div class="flex items-center gap-2">
                  <Badge :label="labelForReachability(row.reachability_state)" :tone="toneForState(row.reachability_state) as any" />
                  <span v-if="row.reachability_note" class="text-xs text-slate-500 dark:text-slate-400">{{ row.reachability_note }}</span>
                </div>
              </td>
              <td class="px-5 py-4">
                <div class="flex items-center gap-2">
                  <Badge :label="row.registration_state" :tone="toneForState(row.registration_state) as any" />
                  <span v-if="row.registration_note" class="text-xs text-slate-500 dark:text-slate-400">{{ row.registration_note }}</span>
                </div>
              </td>
              <td class="px-5 py-4">
                <div class="flex items-center gap-2">
                  <Badge :label="row.invites_state" :tone="toneForState(row.invites_state) as any" />
                  <span v-if="row.invites_state === 'open' && row.invites_display" class="text-xs text-slate-500 dark:text-slate-400">{{ row.invites_display }}</span>
                </div>
              </td>
              <td class="px-5 py-4 text-slate-500 dark:text-slate-400">{{ formatDateTime(row.last_checked_at) }}</td>
              <td class="px-5 py-4 text-slate-500 dark:text-slate-400">{{ formatDateTime(row.last_changed_at) }}</td>
              <td class="px-5 py-4">
                <button
                  v-if="row.errors && row.errors.length"
                  class="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-800 hover:bg-rose-100 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200 dark:hover:bg-rose-950/60"
                  @click="openErrors(row)"
                >
                  查看 ({{ row.errors.length }})
                </button>
                <span v-else class="text-xs text-slate-400">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Modal :open="errorModalOpen" :title="errorModalTitle" @close="errorModalOpen = false">
      <div v-if="!errorModalErrors.length" class="text-sm text-slate-500 dark:text-slate-400">无异常</div>
      <ul v-else class="space-y-2">
        <li
          v-for="(err, i) in errorModalErrors"
          :key="i"
          class="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200"
        >
          {{ err }}
        </li>
      </ul>
    </Modal>
  </div>
</template>
