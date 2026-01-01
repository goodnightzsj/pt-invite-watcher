<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import Badge from "../components/Badge.vue";
import Button from "../components/Button.vue";
import Modal from "../components/Modal.vue";
import TableSkeleton from "../components/TableSkeleton.vue";
import Toggle from "../components/Toggle.vue";
import { api, type SiteRow } from "../api";
import { showToast } from "../toast";

type AutoRefreshMinutes = 1 | 5 | 10 | 30 | 60 | 120 | 360 | 720 | 1440;

const STORAGE_REFRESH_ENABLED = "ptiw_auto_refresh_enabled";
const STORAGE_REFRESH_MINUTES = "ptiw_auto_refresh_minutes";

const loading = ref(false);
const dashboardLoading = ref(false);
const scanRunning = ref(false);
const rowScanDomain = ref("");
const rows = ref<SiteRow[]>([]);
const scanStatus = ref<any>(null);
const scanHint = ref<any>(null);
const allowStateReset = ref(true);

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

const autoRefreshEnabled = ref(localStorage.getItem(STORAGE_REFRESH_ENABLED) === "1");
const autoRefreshMinutes = ref<AutoRefreshMinutes>(
  ([1, 5, 10, 30, 60, 120, 360, 720, 1440] as const).includes(Number(localStorage.getItem(STORAGE_REFRESH_MINUTES)) as any)
    ? (Number(localStorage.getItem(STORAGE_REFRESH_MINUTES)) as AutoRefreshMinutes)
    : 10
);

let timer: number | undefined;
let scanPollTimer: number | undefined;
let inflightPollTimer: number | undefined;

const errorModalOpen = ref(false);
const errorModalTitle = ref("");
const errorModalErrors = ref<string[]>([]);

function toneForState(state: string) {
  if (state === "open" || state === "up") return "green";
  if (state === "closed" || state === "down") return "red";
  return "amber";
}

function parseHttpStatus(note: string | null | undefined): number | null {
  if (!note) return null;
  const m = note.match(/HTTP\s+(\d{3})/i);
  if (!m) return null;
  const v = Number(m[1]);
  return Number.isFinite(v) ? v : null;
}

function reachabilityBadge(row: SiteRow) {
  if (row.reachability_state === "up") {
    const status = parseHttpStatus(row.reachability_note);
    if (status === 403) return { label: "受限", tone: "amber" as const };
    return { label: "正常", tone: "green" as const };
  }
  if (row.reachability_state === "down") return { label: "异常", tone: "red" as const };
  return { label: "未知", tone: "amber" as const };
}

function healthScore(row: SiteRow) {
  let score = 0;
  if (row.reachability_state === "up") score += 4;
  if (row.invites_state === "open") score += 2;
  if (row.registration_state === "open") score += 1;
  return score;
}

function sortedSiteRows(items: SiteRow[]) {
  return [...items].sort((a, b) => {
    const sa = healthScore(a);
    const sb = healthScore(b);
    if (sa !== sb) return sb - sa;

    const nameA = (a.name || a.domain || "").trim();
    const nameB = (b.name || b.domain || "").trim();
    const byName = collator.compare(nameA, nameB);
    if (byName !== 0) return byName;

    return collator.compare(a.domain, b.domain);
  });
}

function formatDateTime(v: string | null | undefined) {
  if (!v) return "-";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" }).format(d);
}

function formatChangedAt(row: SiteRow) {
  if (row.last_changed_at) return formatDateTime(row.last_changed_at);
  if (row.last_checked_at) return "未变更";
  return "-";
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
}

async function waitForDashboardIdle(timeoutMs = 5000) {
  const startedAt = Date.now();
  while (dashboardLoading.value) {
    if (Date.now() - startedAt > timeoutMs) return;
    await sleep(50);
  }
}

async function refresh(opts: { toast?: boolean; silent?: boolean } = {}) {
  if (dashboardLoading.value) return;
  dashboardLoading.value = true;
  if (!opts.silent) loading.value = true;
  try {
    const data = await api.dashboard();
    rows.value = data.rows || [];
    scanStatus.value = data.scan_status;
    scanHint.value = (data as any).scan_hint || null;
    allowStateReset.value = (data as any).ui?.allow_state_reset ?? true;
    if (opts.toast) showToast("数据已刷新", "success", 1800);
  } catch (e: any) {
    if (!opts.silent) showToast(String(e?.message || e || "加载失败"), "error");
  } finally {
    if (!opts.silent) loading.value = false;
    dashboardLoading.value = false;
  }
}

async function refreshManual() {
  if (loading.value) return;
  showToast("正在刷新数据…", "info", 1600);
  await refresh({ toast: true });
}

async function runScan() {
  scanRunning.value = true;
  if (scanPollTimer) {
    window.clearInterval(scanPollTimer);
    scanPollTimer = undefined;
  }
  scanPollTimer = window.setInterval(() => {
    refresh({ silent: true });
  }, 1000);
  void refresh({ silent: true });
  try {
    showToast("开始扫描…", "info", 1600);
    const status = await api.scanRun();
    scanStatus.value = status;
    if (scanPollTimer) {
      window.clearInterval(scanPollTimer);
      scanPollTimer = undefined;
    }
    await waitForDashboardIdle();
    if (status?.ok) {
      const skipped = Number(status?.skipped_in_flight || 0);
      const scanned = Number(status?.scanned_count ?? -1);
      if (scanned === 0 && skipped > 0) {
        showToast("当前无可扫描站点（均在扫描中）", "info", 2400);
      } else if (skipped > 0) {
        showToast(`扫描已完成（跳过 ${skipped} 个在途站点）`, "success", 2400);
      } else {
        showToast("扫描已完成", "success", 2200);
      }
    } else {
      showToast(`扫描失败：${status?.error || "unknown"}`, "error", 4500);
    }
    await refresh();
  } catch (e: any) {
    showToast(String(e?.message || e || "扫描失败"), "error");
  } finally {
    if (scanPollTimer) {
      window.clearInterval(scanPollTimer);
      scanPollTimer = undefined;
    }
    scanRunning.value = false;
  }
}

async function runRowScan(row: SiteRow) {
  if (row.scanning) {
    showToast("该站点正在扫描中，请稍后再试", "info", 2400);
    return;
  }
  if (rowScanDomain.value) return;
  rowScanDomain.value = row.domain;
  showToast(`开始扫描：${row.name || row.domain}`, "info", 1600);
  try {
    const status = await api.scanRunOne(row.domain);
    showToast(
      status?.ok ? `扫描完成：${row.name || row.domain}` : `扫描失败：${status?.error || "unknown"}`,
      status?.ok ? "success" : "error",
      status?.ok ? 2200 : 4500
    );
    await refresh();
  } catch (e: any) {
    showToast(String(e?.message || e || "扫描失败"), "error", 4500);
  } finally {
    rowScanDomain.value = "";
  }
}

async function resetState() {
  if (scanRunning.value || loading.value || rowScanDomain.value) return;
  if (!confirm("确认清空所有站点的扫描结果吗？（不会删除站点配置）")) return;
  try {
    showToast("正在重置站点状态…", "info", 1600);
    await api.stateReset();
    showToast("已重置站点状态", "success", 2200);
    await refresh();
  } catch (e: any) {
    showToast(String(e?.message || e || "重置失败"), "error", 4500);
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

function clearInflightPoll() {
  if (inflightPollTimer) {
    window.clearInterval(inflightPollTimer);
    inflightPollTimer = undefined;
  }
}

function startInflightPoll() {
  if (inflightPollTimer) return;
  void refresh({ silent: true });
  inflightPollTimer = window.setInterval(() => {
    refresh({ silent: true });
  }, 2000);
}

function setupTimer() {
  clearTimer();
  if (!autoRefreshEnabled.value) return;
  timer = window.setInterval(() => {
    refresh();
  }, autoRefreshMinutes.value * 60 * 1000);
}

function formatAutoRefreshInterval(minutes: number) {
  if (minutes > 60) return `${Math.round(minutes / 60)} 小时`;
  return `${minutes} 分钟`;
}

watch(autoRefreshEnabled, (v) => {
  localStorage.setItem(STORAGE_REFRESH_ENABLED, v ? "1" : "0");
  setupTimer();
  showToast(v ? `自动刷新已开启：每 ${formatAutoRefreshInterval(autoRefreshMinutes.value)}` : "自动刷新已关闭", "info", 2400);
});
watch(autoRefreshMinutes, (v) => {
  localStorage.setItem(STORAGE_REFRESH_MINUTES, String(v));
  setupTimer();
  showToast(`自动刷新间隔已更新：${formatAutoRefreshInterval(v)}`, "info", 2400);
});

const hasInflightScan = computed(() => rows.value.some((row) => !!row.scanning));
watch([hasInflightScan, scanRunning], ([hasInflight, running]) => {
  if (running) {
    clearInflightPoll();
    return;
  }
  if (hasInflight) startInflightPoll();
  else clearInflightPoll();
});

onMounted(async () => {
  await refresh();
  setupTimer();
});
onUnmounted(() => {
  clearTimer();
  clearInflightPoll();
  if (scanPollTimer) {
    window.clearInterval(scanPollTimer);
    scanPollTimer = undefined;
  }
});

const hasRows = computed(() => rows.value.length > 0);
const sortedRows = computed(() => sortedSiteRows(rows.value));
</script>

<template>
  <div class="space-y-5">
    <div
      class="rounded-3xl border border-slate-200/60 bg-white p-6 shadow-sm shadow-slate-200/50 transition-shadow hover:shadow-md dark:border-slate-800/60 dark:bg-slate-900/50 dark:shadow-none"
    >
      <div class="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div class="flex items-center gap-2">
             <div class="h-2 w-2 rounded-full bg-brand-500 ring-2 ring-brand-100 dark:ring-brand-900"></div>
             <h2 class="text-lg font-bold text-slate-900 dark:text-white">站点状态</h2>
          </div>
          <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
            管理站点扫描任务与自动更新策略
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50/50 px-4 py-2.5 dark:border-slate-800 dark:bg-slate-900/50">
            <Toggle v-model="autoRefreshEnabled" />
            <span class="text-sm font-medium text-slate-700 dark:text-slate-200">自动刷新</span>
            <div class="mx-2 h-4 w-px bg-slate-200 dark:bg-slate-700"></div>
            <select
              v-model.number="autoRefreshMinutes"
              class="w-auto cursor-pointer border-none bg-transparent py-0 pl-1 pr-7 text-sm font-medium text-slate-900 focus:ring-0 disabled:cursor-not-allowed disabled:opacity-100 disabled:text-slate-500 dark:text-slate-100 dark:disabled:text-slate-300"
              :disabled="!autoRefreshEnabled"
            >
              <option :value="1">1 分钟</option>
              <option :value="5">5 分钟</option>
              <option :value="10">10 分钟</option>
              <option :value="30">30 分钟</option>
              <option :value="60">60 分钟</option>
              <option :value="120">2 小时</option>
              <option :value="360">6 小时</option>
              <option :value="720">12 小时</option>
              <option :value="1440">24 小时</option>
            </select>
          </div>
          <div class="flex items-center gap-2">
            <Button variant="primary" :disabled="scanRunning" :loading="scanRunning" @click="runScan">
              {{ scanRunning ? "扫描中…" : "立即扫描" }}
            </Button>
            <Button :disabled="loading" @click="refreshManual">
              刷新数据
            </Button>
            <Button
              v-if="allowStateReset"
              variant="danger"
              :disabled="scanRunning || loading || !!rowScanDomain"
              title="清空扫描结果（不影响站点配置）"
              @click="resetState"
            >
              重置状态
            </Button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="scanHint"
      class="rounded-2xl border border-brand-200 bg-brand-50 p-5 shadow-sm dark:border-brand-900 dark:bg-brand-950/40"
    >
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-base font-semibold text-brand-900 dark:text-brand-100">提示</div>
          <div class="mt-1 text-sm text-brand-800/80 dark:text-brand-200/80">
            检测到配置已导入/更新。站点状态需要扫描后生成/刷新。
          </div>
        </div>
        <Button variant="primary" :disabled="scanRunning" :loading="scanRunning" @click="runScan">
          {{ scanRunning ? "扫描中…" : "立即扫描" }}
        </Button>
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
      <div v-if="!scanStatus.ok" class="mt-3 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm text-danger-800 dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-200">
        失败：{{ scanStatus.error || "unknown" }}
        <div class="mt-1 text-danger-700/80 dark:text-danger-200/80">请检查站点配置与网络连通性；导入/新增站点后需先点击“立即扫描”。</div>
      </div>
      <div
        v-else-if="scanStatus.warning"
        class="mt-3 rounded-xl border border-warning-200 bg-warning-50 p-3 text-sm text-warning-900 dark:border-warning-900 dark:bg-warning-950/40 dark:text-warning-200"
      >
        警告：{{ scanStatus.warning }}
      </div>
    </div>

    <div
      class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div class="border-b border-slate-100 px-4 py-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        <span v-if="loading && !hasRows">加载中…</span>
        <span v-else-if="hasRows">共 {{ rows.length }} 个站点</span>
        <span v-else>暂无扫描数据：请先在“站点管理”配置/导入站点，然后点击“立即扫描”。</span>
      </div>

      <!-- Scanning progress bar -->
      <div
        v-if="scanRunning || hasInflightScan"
        class="h-1 w-full overflow-hidden bg-slate-100 dark:bg-slate-800"
      >
        <div class="h-full w-full animate-scan-progress bg-gradient-to-r from-brand-500 via-purple-500 to-brand-500" />
      </div>

      <!-- Skeleton loading -->
      <div v-if="loading && !hasRows" class="overflow-x-auto">
        <TableSkeleton :rows="5" :cols="7" />
      </div>

      <div v-if="hasRows || (!loading && !hasRows)" class="overflow-x-auto max-h-[calc(100vh-300px)]">
        <table class="min-w-full text-left text-sm">
          <thead class="sticky top-0 z-10 bg-slate-50 border-b border-slate-200/70 text-xs uppercase tracking-wider text-slate-500 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-400">
            <tr>
              <th class="px-6 py-4 font-semibold min-w-[180px] max-w-[280px]">站点 / 域名</th>
              <th class="hidden md:table-cell px-6 py-4 font-semibold w-24">引擎</th>
              <th class="px-6 py-4 font-semibold w-32">可访问</th>
              <th class="px-6 py-4 font-semibold w-32">开放注册</th>
              <th class="px-6 py-4 font-semibold w-32">可用邀请</th>
              <th class="hidden lg:table-cell px-6 py-4 font-semibold min-w-[160px]">最后检查</th>
              <th class="px-6 py-4 font-semibold text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800/60">
            <tr v-for="row in sortedRows" :key="row.domain" class="group transition-colors duration-150 hover:bg-slate-50/80 dark:hover:bg-slate-800/30">
              <!-- Site & Domain Combined -->
              <td class="px-6 py-4">
                <div class="flex flex-col">
                  <span class="font-semibold text-slate-700 group-hover:text-warning-600 dark:text-slate-200 dark:group-hover:text-warning-400 transition-colors">{{ row.name || "-" }}</span>
                  <a class="mt-0.5 text-xs text-brand-500 hover:text-brand-600 hover:underline dark:text-brand-400 dark:hover:text-brand-300" :href="row.url" target="_blank" rel="noreferrer">
                    {{ row.domain }}
                  </a>
                </div>
              </td>
              
              <td class="hidden md:table-cell px-6 py-4">
                <Badge :label="row.engine || 'unknown'" tone="slate" class="rounded-md px-2 py-1 text-[10px]" />
              </td>

              <td class="px-6 py-4">
                <div class="flex items-center gap-2">
                  <Badge class="shrink-0" :label="reachabilityBadge(row).label" :tone="reachabilityBadge(row).tone as any" />
                  <span v-if="row.reachability_note" class="line-clamp-1 max-w-[120px] text-xs text-slate-400" :title="row.reachability_note">
                    {{ row.reachability_note }}
                  </span>
                </div>
              </td>

              <td class="px-6 py-4">
                <div class="flex items-center gap-2">
                  <a
                    v-if="row.registration_state === 'open' && row.registration_url"
                    :href="row.registration_url"
                    target="_blank"
                    rel="noreferrer"
                    class="shrink-0"
                    :title="`打开注册页：${row.registration_url}`"
                  >
                    <Badge :label="row.registration_state" :tone="toneForState(row.registration_state) as any" />
                  </a>
                  <Badge v-else class="shrink-0" :label="row.registration_state" :tone="toneForState(row.registration_state) as any" />
                  <span v-if="row.registration_note" class="line-clamp-1 max-w-[120px] text-xs text-slate-400" :title="row.registration_note">
                    {{ row.registration_note }}
                  </span>
                </div>
              </td>

              <td class="px-6 py-4">
                <div class="flex items-center gap-2">
                  <a
                    v-if="row.invites_state === 'open' && row.invite_url"
                    :href="row.invite_url"
                    target="_blank"
                    rel="noreferrer"
                    class="shrink-0"
                    :title="`打开邀请页：${row.invite_url}`"
                  >
                    <Badge :label="row.invites_state" :tone="toneForState(row.invites_state) as any" />
                  </a>
                  <Badge v-else class="shrink-0" :label="row.invites_state" :tone="toneForState(row.invites_state) as any" />
                  <span v-if="row.invites_state === 'open' && row.invites_display" class="line-clamp-1 max-w-[120px] text-xs text-slate-400">
                    {{ row.invites_display }}
                  </span>
                </div>
              </td>

              <td class="hidden lg:table-cell px-6 py-4">
                 <div class="text-xs text-slate-500 dark:text-slate-400">
                   <div>最新检查：{{ formatDateTime(row.last_checked_at) }}</div>
                   <div class="mt-0.5 scale-90 origin-left opacity-60">上次变更时间：{{ formatChangedAt(row) }}</div>
                 </div>
              </td>

              <td class="px-6 py-4 text-right">
                <div class="flex items-center justify-end gap-2">
                  <button
                    class="rounded-lg p-2 text-slate-400 transition-colors hover:bg-brand-50 hover:text-brand-600 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:bg-brand-500/10 dark:hover:text-brand-300"
                    :disabled="scanRunning || loading || rowScanDomain === row.domain || row.scanning"
                    @click="runRowScan(row)"
                    title="扫描此站"
                  >
                     <svg v-if="rowScanDomain === row.domain || row.scanning" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                     <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-refresh-cw"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg>
                  </button>
                  <button
                     v-if="row.errors && row.errors.length"
                     class="rounded-lg p-2 text-danger-500 transition-colors hover:bg-danger-50 hover:text-danger-600 dark:hover:bg-danger-900/20"
                     @click="openErrors(row)"
                     :title="`查看错误 (${row.errors.length})`"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-alert-circle"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
                  </button>
                </div>
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
          class="rounded-xl border border-danger-200 bg-danger-50 px-3 py-2 text-sm text-danger-800 dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-200"
        >
          {{ err }}
        </li>
      </ul>
    </Modal>
  </div>
</template>
