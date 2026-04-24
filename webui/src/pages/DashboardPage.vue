<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Globe, UserPlus, Ticket, AlertTriangle, RefreshCw, AlertCircle, Loader2, Download } from "lucide-vue-next";

import Badge from "../components/Badge.vue";
import Card from "../components/Card.vue";
import Button from "../components/Button.vue";
import PageHeader from "../components/PageHeader.vue";
import Modal from "../components/Modal.vue";
import SiteDetailModal from "../components/SiteDetailModal.vue";
import SiteCard from "../components/SiteCard.vue";
import SiteIcon from "../components/SiteIcon.vue";
import EmptyState from "../components/EmptyState.vue";
import TableSkeleton from "../components/TableSkeleton.vue";
import Toggle from "../components/Toggle.vue";
import Tooltip from "../components/Tooltip.vue";
import RelativeTime from "../components/RelativeTime.vue";
import { api, type SiteRow, type ScanStatus } from "../api";
import { showToast } from "../toast";
import { formatLocalTime, formatRelativeTime } from "../utils/date";

const loading = ref(false);
const dashboardLoading = ref(false);
const scanRunning = ref(false);
const scanningDomains = ref<Set<string>>(new Set());
const rows = ref<SiteRow[]>([]);
const scanStatus = ref<ScanStatus | null>(null);
const scanHint = ref<{ reason: string; at: string; changed?: string[] } | null>(null);
const selectedSite = ref<SiteRow | null>(null);
const allowStateReset = ref(true);

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

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

function changedLabel(row: SiteRow): string {
  if (row.last_changed_at) return "";  // RelativeTime component renders it
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
    if (e?.status === 409) {
      showToast("扫描已在进行中", "info", 2400);
      await refresh({ silent: true });
    } else {
      showToast(String(e?.message || e || "扫描失败"), "error");
    }
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
  if (scanningDomains.value.has(row.domain)) {
    showToast("该站点正在扫描中", "info", 2400);
    return;
  }
  scanningDomains.value.add(row.domain);
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
    if (e?.status === 409) {
      showToast("该站点正在扫描中，请稍后再试", "info", 2400);
    } else {
      showToast(String(e?.message || e || "扫描失败"), "error", 4500);
    }
  } finally {
    scanningDomains.value.delete(row.domain);
  }
}

import { confirm } from "../confirm";

async function resetState() {
  if (scanRunning.value || loading.value || scanningDomains.value.size > 0) return;
  if (!(await confirm("确认清空所有站点的扫描结果吗？（不会删除站点配置）"))) return;
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
});
onUnmounted(() => {
  clearInflightPoll();
  if (scanPollTimer) {
    window.clearInterval(scanPollTimer);
    scanPollTimer = undefined;
  }
  if (wsRefreshRaf != null) {
    window.cancelAnimationFrame(wsRefreshRaf);
    wsRefreshRaf = undefined;
  }
  if (scanProgressClearTimer) {
    window.clearTimeout(scanProgressClearTimer);
    scanProgressClearTimer = undefined;
  }
});

// WS real-time updates — coalesce bursts within one animation frame to avoid flicker.
import { useWS } from "../ws";
import { WS_DASHBOARD_UPDATE, WS_SCAN_PROGRESS } from "../ws_events";
let wsRefreshRaf: number | undefined;
useWS(WS_DASHBOARD_UPDATE, () => {
  if (wsRefreshRaf != null) return;
  wsRefreshRaf = window.requestAnimationFrame(() => {
    wsRefreshRaf = undefined;
    refresh({ silent: true });
  });
});

// Per-site scan progress — updates a small counter without refetching the whole dashboard.
const scanProgress = ref<{ total: number; completed: number; domain: string; elapsedMs: number | null } | null>(null);
let scanProgressClearTimer: number | undefined;
useWS(WS_SCAN_PROGRESS, (data: any) => {
  if (!data) return;
  const total = Number(data.total || 0);
  if (total <= 0) {
    scanProgress.value = null;
    return;
  }
  const rawElapsed = data.elapsed_ms;
  const elapsedMs = typeof rawElapsed === "number" && Number.isFinite(rawElapsed) ? rawElapsed : null;
  scanProgress.value = {
    total,
    completed: Math.min(total, Number(data.completed || 0)),
    domain: String(data.domain || ""),
    elapsedMs,
  };
  if (scanProgressClearTimer) window.clearTimeout(scanProgressClearTimer);
  if (scanProgress.value.completed >= total) {
    // Hold the final frame for a beat, then let it fade.
    scanProgressClearTimer = window.setTimeout(() => {
      scanProgress.value = null;
    }, 1500);
  }
});

// Screen-reader announcement throttled to *milestone* granularity: site-change
// transitions and scan completion. Binding aria-live directly to the computed
// `${completed}/${total}` would re-read the number on every broadcast tick —
// auditory spam. Updating a backing ref only on meaningful transitions keeps
// the announcement cadence to one utterance per site (plus a final "完成").
const a11yScanAnnouncement = ref("");
watch(
  () => ({ d: scanProgress.value?.domain || "", c: scanProgress.value?.completed || 0, t: scanProgress.value?.total || 0, running: scanRunning.value }),
  (next, prev) => {
    if (next.running && !prev?.running && !next.t) {
      a11yScanAnnouncement.value = "扫描进行中";
      return;
    }
    if (next.t > 0 && next.c >= next.t && !(prev && prev.c >= prev.t && prev.t === next.t)) {
      a11yScanAnnouncement.value = `扫描完成：${next.c} / ${next.t}`;
      return;
    }
    if (next.d && next.d !== prev?.d) {
      a11yScanAnnouncement.value = next.t > 0 ? `正在扫描 ${next.d} (${next.c} / ${next.t})` : `正在扫描 ${next.d}`;
    }
  }
);

function formatElapsed(ms: number | null): string {
  if (ms == null) return "";
  if (ms < 1000) return `${ms}ms`;
  const s = (ms / 1000);
  return s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`;
}

type FilterMode = "all" | "unreachable" | "openReg" | "openInvite";

// Hydrate from URL so refreshing or sharing a filtered view preserves context.
// e.g. `/dashboard?filter=openReg` reopens the "开放注册" filter on mount.
const route = useRoute();
const router = useRouter();
const initialFilter = (route.query.filter as FilterMode | undefined) || "all";
const validFilters: readonly FilterMode[] = ["all", "unreachable", "openReg", "openInvite"];
const filterMode = ref<FilterMode>(
  validFilters.includes(initialFilter as FilterMode) ? (initialFilter as FilterMode) : "all"
);

function toggleFilter(mode: FilterMode) {
  filterMode.value = filterMode.value === mode ? "all" : mode;
}

// Mirror to URL via `replace` (not `push`) so the back button doesn't stack
// every filter toggle the user makes. Wrapped in watch with flush:"post" to
// coalesce with Vue's render batching.
let syncingFilterQuery = false;
watch(
  filterMode,
  (mode) => {
    if (syncingFilterQuery) return;
    syncingFilterQuery = true;
    const q: Record<string, string> = { ...route.query } as any;
    if (mode === "all") delete q.filter;
    else q.filter = mode;
    router.replace({ query: q }).catch(() => { /* NavigationDuplicated is safe to ignore */ }).finally(() => {
      syncingFilterQuery = false;
    });
  },
  { flush: "post" }
);

const hasRows = computed(() => rows.value.length > 0);
const filteredRows = computed(() => {
  if (filterMode.value === "unreachable") return rows.value.filter((r) => r.reachability_state === "down");
  if (filterMode.value === "openReg") return rows.value.filter((r) => r.registration_state === "open");
  if (filterMode.value === "openInvite") return rows.value.filter((r) => r.invites_state === "open");
  return rows.value;
});
const sortedRows = computed(() => sortedSiteRows(filteredRows.value));

/**
 * CSV export of the currently filtered + sorted site list.
 *
 * Exports what the user sees — filter chips flow through, so exporting while
 * the "异常站点" filter is active gives them a CSV of just those rows. Uses
 * the proper CSV escaping (quote fields with commas / quotes / newlines and
 * double any embedded quotes), not a naive `.join(",")`.
 *
 * Includes a BOM so Excel on Windows doesn't mojibake Chinese. The file name
 * embeds an ISO-like local timestamp so multiple exports don't collide.
 */
function csvEscape(v: unknown): string {
  const s = v == null ? "" : String(v);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function exportCsv() {
  const rows = sortedRows.value;
  if (!rows.length) {
    showToast("当前没有可导出的站点", "info", 2000);
    return;
  }
  const header = ["站点", "域名", "URL", "引擎", "连通性", "可访问备注", "注册", "注册备注", "邀请", "可用邀请", "最后检查", "最后变更"];
  const body = rows.map((r) => [
    r.name || "",
    r.domain,
    r.url,
    r.engine || "",
    r.reachability_state,
    r.reachability_note || "",
    r.registration_state,
    r.registration_note || "",
    r.invites_state,
    r.invites_available ?? "",
    r.last_checked_at || "",
    r.last_changed_at || "",
  ]);
  const csv = [header, ...body].map((row) => row.map(csvEscape).join(",")).join("\n");
  // BOM → Excel auto-detects UTF-8 and doesn't garble Chinese characters.
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  a.download = `pt-sites-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  showToast(`已导出 ${rows.length} 个站点为 CSV`, "success", 2200);
}

const stats = computed(() => {
  const r = rows.value;
  return {
    total: r.length,
    openReg: r.filter((x) => x.registration_state === "open").length,
    openInvite: r.filter((x) => x.invites_state === "open").length,
    unreachable: r.filter((x) => x.reachability_state === "down").length,
  };
});
</script>

<template>
  <div class="space-y-5">
    <PageHeader title="站点状态" description="管理站点扫描任务">
      <template #actions>
        <div class="flex gap-2">
          <Button variant="primary" :disabled="scanRunning" :loading="scanRunning" @click="runScan"
            class="flex-1 sm:flex-none">
            {{ scanRunning ? "扫描中…" : "立即扫描" }}
          </Button>
          <Button
            :disabled="!hasRows"
            title="导出当前筛选下的站点列表为 CSV（Excel 可直接打开）"
            @click="exportCsv"
            class="flex-1 sm:flex-none"
          >
            <Download class="mr-1 h-4 w-4" aria-hidden="true" />
            导出 CSV
          </Button>
          <Button v-if="allowStateReset" variant="danger" :disabled="scanRunning || loading || scanningDomains.size > 0"
            title="清空扫描结果（不影响站点配置）" @click="resetState" class="flex-1 sm:flex-none">
            重置状态
          </Button>
        </div>
      </template>
    </PageHeader>

    <!-- Stat Grid — each card acts as a toggle filter for the site list below. -->
    <div v-if="hasRows || loading" class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <button type="button" @click="toggleFilter('all')"
        class="text-left outline-none focus-visible:ring-2 focus-visible:ring-brand-500 rounded-2xl">
        <Card :hoverable="true" class="relative overflow-hidden" :class="filterMode === 'all' ? 'ring-2 ring-brand-400/40' : ''">
          <div class="text-sm font-medium text-slate-500 dark:text-slate-300">总站点</div>
          <div :key="stats.total" class="count-number relative z-10 mt-2 text-3xl font-bold tabular-nums text-slate-900 dark:text-white">{{ stats.total }}</div>
          <Globe class="absolute -bottom-3 -right-3 h-16 w-16 text-slate-400 opacity-10 dark:text-slate-200 dark:opacity-10" />
        </Card>
      </button>
      <button type="button" @click="toggleFilter('openReg')"
        class="text-left outline-none focus-visible:ring-2 focus-visible:ring-brand-500 rounded-2xl">
        <Card :hoverable="true" class="relative overflow-hidden" :class="filterMode === 'openReg' ? 'ring-2 ring-emerald-400/50' : ''">
          <div class="text-sm font-medium text-slate-500 dark:text-slate-300">开放注册</div>
          <div :key="stats.openReg" class="count-number relative z-10 mt-2 text-3xl font-bold tabular-nums text-emerald-600 dark:text-emerald-400">{{ stats.openReg }}</div>
          <UserPlus class="absolute -bottom-3 -right-3 h-16 w-16 text-emerald-500 opacity-10 dark:text-emerald-400 dark:opacity-10" />
        </Card>
      </button>
      <button type="button" @click="toggleFilter('openInvite')"
        class="text-left outline-none focus-visible:ring-2 focus-visible:ring-brand-500 rounded-2xl">
        <Card :hoverable="true" class="relative overflow-hidden" :class="filterMode === 'openInvite' ? 'ring-2 ring-blue-400/50' : ''">
          <div class="text-sm font-medium text-slate-500 dark:text-slate-300">开放邀请</div>
          <div :key="stats.openInvite" class="count-number relative z-10 mt-2 text-3xl font-bold tabular-nums text-blue-600 dark:text-blue-400">{{ stats.openInvite }}</div>
          <Ticket class="absolute -bottom-3 -right-3 h-16 w-16 text-blue-500 opacity-10 dark:text-blue-400 dark:opacity-10" />
        </Card>
      </button>
      <button type="button" @click="toggleFilter('unreachable')"
        class="text-left outline-none focus-visible:ring-2 focus-visible:ring-rose-500 rounded-2xl">
        <Card :hoverable="true" class="relative overflow-hidden transition-shadow"
          :class="[
            stats.unreachable > 0 ? 'ring-2 ring-rose-500/40 shadow-rose-500/20' : '',
            filterMode === 'unreachable' ? 'ring-2 ring-rose-500/70' : '',
          ]">
          <div class="text-sm font-medium" :class="stats.unreachable > 0 ? 'text-rose-700 dark:text-rose-200' : 'text-slate-500 dark:text-slate-300'">异常站点</div>
          <div :key="stats.unreachable" class="count-number relative z-10 mt-2 text-3xl font-bold tabular-nums" :class="stats.unreachable > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-700 dark:text-slate-200'">{{ stats.unreachable }}</div>
          <AlertTriangle class="absolute -bottom-3 -right-3 h-16 w-16 opacity-10"
            :class="stats.unreachable > 0 ? 'text-rose-500 dark:text-rose-400' : 'text-slate-400 dark:text-slate-200'" />
        </Card>
      </button>
    </div>

    <!-- Active filter pill -->
    <div v-if="hasRows && filterMode !== 'all'" class="flex items-center gap-2 text-sm">
      <span class="text-slate-500 dark:text-slate-300">已筛选：</span>
      <span class="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-slate-700 dark:bg-slate-800 dark:text-slate-200">
        {{ filterMode === 'unreachable' ? '异常站点' : filterMode === 'openReg' ? '开放注册' : '开放邀请' }}
        <button class="text-slate-400 hover:text-slate-700 dark:hover:text-slate-100" @click="filterMode = 'all'" title="清除筛选" aria-label="清除筛选">×</button>
      </span>
      <span class="text-xs text-slate-400 dark:text-slate-400">{{ sortedRows.length }} / {{ rows.length }} 站点</span>
    </div>

    <div v-if="scanHint"
      class="rounded-2xl border border-brand-200 bg-brand-50 p-5 shadow-sm dark:border-brand-900 dark:bg-brand-950/40">
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

    <Card v-if="scanStatus" :hoverable="false">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-base font-semibold">扫描状态</div>
          <div class="mt-1 text-sm text-slate-500 dark:text-slate-300">
            最后运行：{{ formatLocalTime(scanStatus.last_run_at) }} · 站点数：{{ scanStatus.site_count || 0 }}
          </div>
        </div>
        <Badge :label="scanStatus.ok ? 'ok' : 'fail'" :tone="scanStatus.ok ? 'green' : 'red'" />
      </div>
      <div v-if="!scanStatus.ok"
        class="mt-3 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm text-danger-800 dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-200">
        失败：{{ scanStatus.error || "unknown" }}
        <div class="mt-1 text-danger-700/80 dark:text-danger-200/80">请检查站点配置与网络连通性；导入/新增站点后需先点击“立即扫描”。</div>
      </div>
      <div v-else-if="scanStatus.warning"
        class="mt-3 rounded-xl border border-warning-200 bg-warning-50 p-3 text-sm text-warning-900 dark:border-warning-900 dark:bg-warning-950/40 dark:text-warning-200">
        警告：{{ scanStatus.warning }}
      </div>
    </Card>

    <EmptyState v-if="!loading && !hasRows" title="暂无扫描数据" description="请先在“站点管理”配置或导入站点，然后点击“立即扫描”。" actionText="去配置站点"
      @action="$router.push('/sites')" />

    <Card v-else padding="none" :hoverable="false">
      <div class="overflow-hidden rounded-2xl">
        <div
          class="border-b border-slate-200/60 bg-slate-50/50 px-4 py-4 text-sm font-medium text-slate-500 backdrop-blur-sm dark:border-slate-800/60 dark:bg-slate-900/50 dark:text-slate-300">
          <span v-if="loading && !hasRows">加载中…</span>
          <span v-else>共 {{ rows.length }} 个站点</span>
        </div>

        <!-- Scanning progress bar: determinate if we have live progress, otherwise indeterminate. -->
        <div v-if="scanRunning || hasInflightScan || scanProgress" class="relative">
          <div
            class="h-1 w-full overflow-hidden bg-slate-100 dark:bg-slate-800"
            role="progressbar"
            :aria-valuemin="0"
            :aria-valuemax="scanProgress?.total || 100"
            :aria-valuenow="scanProgress?.completed || 0"
            :aria-valuetext="scanProgress ? `已扫描 ${scanProgress.completed} / ${scanProgress.total}` : '扫描进行中'"
          >
            <div
              v-if="scanProgress && scanProgress.total > 0"
              class="h-full bg-gradient-to-r from-brand-500 via-purple-500 to-brand-500 transition-[width] duration-300 ease-out"
              :style="{ width: `${Math.min(100, Math.round((scanProgress.completed / scanProgress.total) * 100))}%` }"
            />
            <div v-else class="h-full w-full animate-scan-progress bg-gradient-to-r from-brand-500 via-purple-500 to-brand-500" />
          </div>
          <div v-if="scanProgress && scanProgress.total > 0"
            class="pointer-events-none absolute right-3 top-1 flex items-center gap-2 text-[11px] font-medium text-slate-500 tabular-nums dark:text-slate-300">
            <span>{{ scanProgress.completed }} / {{ scanProgress.total }}</span>
            <span v-if="scanProgress.domain" class="max-w-[12rem] truncate text-slate-400 dark:text-slate-400">{{ scanProgress.domain }}</span>
            <span v-if="scanProgress.elapsedMs != null" class="text-slate-400 dark:text-slate-500">· {{ formatElapsed(scanProgress.elapsedMs) }}</span>
          </div>
          <!--
            Screen-reader-only polite announcement of scan progress milestones.
            Speaks only when the current site changes or the scan finishes; we
            don't want "扫描中 x/y" shouted on every tick. Invisible to sighted
            users (the visual progress bar does the job for them).
          -->
          <div class="sr-only" role="status" aria-live="polite" aria-atomic="true">
            {{ a11yScanAnnouncement }}
          </div>
        </div>

        <!-- Skeleton loading -->
        <div v-if="loading && !hasRows" class="overflow-x-auto">
          <TableSkeleton :rows="5" :cols="7" />
        </div>

        <!-- Mobile: Card View -->
        <div v-if="hasRows" class="md:hidden space-y-3 p-4">
          <TransitionGroup name="list">
            <SiteCard v-for="(row, index) in sortedRows" :key="row.domain" :site="row" :style="{ '--i': index }"
              @click="selectedSite = row" />
          </TransitionGroup>
        </div>

        <!-- Desktop: Table View -->
        <div v-if="hasRows || (!loading && !hasRows)" class="hidden md:block overflow-x-auto max-h-[calc(100vh-300px)]">
          <table class="min-w-full text-left text-sm relative border-collapse">
            <thead
              class="sticky top-0 z-10 border-b border-white/10 bg-white/40 text-xs font-semibold uppercase tracking-wider text-slate-500 backdrop-blur-xl dark:border-white/5 dark:bg-slate-900/40 dark:text-slate-300">
              <tr>
                <th class="px-6 py-4 min-w-[180px] max-w-[280px]">站点 / 域名</th>
                <th class="hidden md:table-cell px-6 py-4 w-24">引擎</th>
                <th class="px-6 py-4 w-32">可访问</th>
                <th class="px-6 py-4 w-32">开放注册</th>
                <th class="px-6 py-4 w-32">可用邀请</th>
                <th class="hidden lg:table-cell px-6 py-4 min-w-[160px]">最后检查</th>
                <th class="px-6 py-4 text-right">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800/40">
              <TransitionGroup name="list" appear>
                <tr v-for="(row, index) in sortedRows" :key="row.domain" :style="{ '--i': index }"
                  class="group table-row-hover transition-colors duration-150 hover:bg-brand-50/40 dark:hover:bg-brand-950/20"
                  :class="row.scanning ? 'row-scanning' : ''">
                  <!-- Site & Domain Combined -->
                  <td class="px-6 py-4">
                    <div class="flex items-center gap-3">
                      <div class="h-10 w-10">
                        <SiteIcon :url="row.url" :name="row.name || '-'" :reachability="row.reachability_state" />
                      </div>
                      <div class="flex flex-col">
                        <span
                          class="cursor-pointer font-semibold text-slate-700 transition-colors hover:text-brand-600 dark:text-slate-200 dark:hover:text-brand-400"
                          @click="selectedSite = row">{{ row.name || "-" }}</span>
                        <a class="mt-0.5 text-xs text-brand-500 hover:text-brand-600 hover:underline dark:text-brand-400 dark:hover:text-brand-300"
                          :href="row.url" target="_blank" rel="noreferrer" @click.stop>
                          {{ row.domain }}
                        </a>
                      </div>
                    </div>
                  </td>

                  <td class="hidden md:table-cell px-6 py-4">
                    <Badge :label="row.engine || 'unknown'" tone="slate" class="rounded-md px-2 py-1 text-[10px]" />
                  </td>

                  <td class="px-6 py-4">
                    <div class="flex items-center gap-2">
                      <Badge class="shrink-0" :label="reachabilityBadge(row).label"
                        :tone="reachabilityBadge(row).tone as any" />
                      <Tooltip v-if="row.reachability_note" :text="row.reachability_note">
                        <span class="status-note line-clamp-1 max-w-[120px] cursor-help"
                          :class="reachabilityBadge(row).tone === 'red' ? 'danger' : reachabilityBadge(row).tone === 'green' ? 'success' : 'warning'">
                          {{ row.reachability_note }}
                        </span>
                      </Tooltip>
                    </div>
                  </td>

                  <td class="px-6 py-4">
                    <div class="flex items-center gap-2">
                      <a v-if="row.registration_state === 'open' && row.registration_url" :href="row.registration_url"
                        target="_blank" rel="noreferrer" class="shrink-0" :title="`打开注册页：${row.registration_url}`">
                        <Badge :label="row.registration_state" :tone="toneForState(row.registration_state) as any" />
                      </a>
                      <Badge v-else class="shrink-0" :label="row.registration_state"
                        :tone="toneForState(row.registration_state) as any" />
                      <Tooltip v-if="row.registration_note" :text="row.registration_note">
                        <span class="status-note line-clamp-1 max-w-[120px] cursor-help"
                          :class="toneForState(row.registration_state) === 'green' ? 'success' : toneForState(row.registration_state) === 'red' ? 'danger' : 'warning'">
                          {{ row.registration_note }}
                        </span>
                      </Tooltip>
                    </div>
                  </td>

                  <td class="px-6 py-4">
                    <div class="flex items-center gap-2">
                      <a v-if="row.invites_state === 'open' && row.invite_url" :href="row.invite_url" target="_blank"
                        rel="noreferrer" class="shrink-0" :title="`打开邀请页：${row.invite_url}`">
                        <Badge :label="row.invites_state" :tone="toneForState(row.invites_state) as any" />
                      </a>
                      <Badge v-else class="shrink-0" :label="row.invites_state"
                        :tone="toneForState(row.invites_state) as any" />
                      <span v-if="row.invites_state === 'open' && row.invites_display"
                        class="status-note success line-clamp-1 max-w-[120px] tabular-nums">
                        {{ row.invites_display }}
                      </span>
                    </div>
                  </td>

                  <td class="hidden lg:table-cell px-6 py-4">
                    <div class="text-xs text-slate-500 dark:text-slate-300">
                      <div>最新检查：<RelativeTime :ts="row.last_checked_at" /></div>
                      <div class="mt-0.5 scale-90 origin-left opacity-60">
                        上次变更时间：<RelativeTime v-if="row.last_changed_at" :ts="row.last_changed_at" />
                        <span v-else>{{ changedLabel(row) }}</span>
                      </div>
                    </div>
                  </td>

                  <td class="px-6 py-4 text-right">
                    <div class="flex items-center justify-end gap-2">
                      <button
                        class="rounded-lg p-2 text-slate-400 transition-colors hover:bg-brand-50 hover:text-brand-600 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:bg-brand-500/10 dark:hover:text-brand-300"
                        :disabled="scanRunning || loading || scanningDomains.has(row.domain) || row.scanning"
                        @click="runRowScan(row)" title="扫描此站"
                        :aria-label="`扫描 ${row.name || row.domain}`">
                        <Loader2 v-if="scanningDomains.has(row.domain) || row.scanning"
                          class="h-4 w-4 animate-spin opacity-50" />
                        <RefreshCw v-else class="h-4 w-4" />
                      </button>
                      <button v-if="row.errors && row.errors.length"
                        class="rounded-lg p-2 text-danger-500 transition-colors hover:bg-danger-50 hover:text-danger-600 dark:hover:bg-danger-900/20"
                        @click="openErrors(row)" :title="`查看错误 (${row.errors.length})`"
                        :aria-label="`查看 ${row.name || row.domain} 的 ${row.errors.length} 条错误`">
                        <AlertCircle class="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              </TransitionGroup>
            </tbody>
          </table>
        </div>
      </div>
    </Card>

    <!-- Modals -->


    <SiteDetailModal :open="!!selectedSite" :site="selectedSite" @close="selectedSite = null" />

    <Modal :open="errorModalOpen" :title="errorModalTitle" @close="errorModalOpen = false">
      <div v-if="!errorModalErrors.length" class="text-sm text-slate-500 dark:text-slate-300">无异常</div>
      <ul v-else class="space-y-2">
        <li v-for="(err, i) in errorModalErrors" :key="i"
          class="rounded-xl border border-danger-200 bg-danger-50 px-3 py-2 text-sm text-danger-800 dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-200">
          {{ err }}
        </li>
      </ul>
    </Modal>


  </div>
</template>
