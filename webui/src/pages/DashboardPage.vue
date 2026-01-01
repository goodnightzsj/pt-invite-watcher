<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { Globe, UserPlus, Ticket, AlertTriangle, RefreshCw, AlertCircle, Loader2 } from "lucide-vue-next";

import Badge from "../components/Badge.vue";
import Button from "../components/Button.vue";
import PageHeader from "../components/PageHeader.vue";
import Modal from "../components/Modal.vue";
import SiteDetailModal from "../components/SiteDetailModal.vue";
import SiteCard from "../components/SiteCard.vue";
import SiteIcon from "../components/SiteIcon.vue";
import EmptyState from "../components/EmptyState.vue";
import TableSkeleton from "../components/TableSkeleton.vue";
import Toggle from "../components/Toggle.vue";
import { api, type SiteRow } from "../api";
import { showToast } from "../toast";

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
    showToast(String(e?.message || e || "扫描失败"), "error", 4500);
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
});

// WS real-time updates
import { useWS } from "../ws";
useWS("dashboard_update", () => {
  refresh({ silent: true });
});

const hasRows = computed(() => rows.value.length > 0);
const sortedRows = computed(() => sortedSiteRows(rows.value));

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
            <Button variant="primary" :disabled="scanRunning" :loading="scanRunning" @click="runScan" class="flex-1 sm:flex-none">
              {{ scanRunning ? "扫描中…" : "立即扫描" }}
            </Button>
            <Button
              v-if="allowStateReset"
              variant="danger"
              :disabled="scanRunning || loading || scanningDomains.size > 0"
              title="清空扫描结果（不影响站点配置）"
              @click="resetState"
              class="flex-1 sm:flex-none"
            >
              重置状态
            </Button>
          </div>
      </template>
    </PageHeader>

    <!-- Stat Grid -->
    <div v-if="hasRows || loading" class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <div class="relative overflow-hidden rounded-2xl border border-slate-200/60 bg-white p-5 shadow-sm dark:border-slate-800/60 dark:bg-slate-900/50">
        <div class="text-sm font-medium text-slate-500 dark:text-slate-400">总站点</div>
        <div class="relative z-10 mt-2 text-3xl font-bold text-slate-900 dark:text-white">{{ stats.total }}</div>
        <Globe class="absolute -bottom-3 -right-3 h-16 w-16 text-slate-400 opacity-10 dark:text-slate-200 dark:opacity-10" />
      </div>
      <div class="relative overflow-hidden rounded-2xl border border-slate-200/60 bg-white p-5 shadow-sm dark:border-slate-800/60 dark:bg-slate-900/50">
        <div class="text-sm font-medium text-slate-500 dark:text-slate-400">开放注册</div>
        <div class="relative z-10 mt-2 text-3xl font-bold text-emerald-600 dark:text-emerald-400">{{ stats.openReg }}</div>
        <UserPlus class="absolute -bottom-3 -right-3 h-16 w-16 text-emerald-500 opacity-10 dark:text-emerald-400 dark:opacity-10" />
      </div>
      <div class="relative overflow-hidden rounded-2xl border border-slate-200/60 bg-white p-5 shadow-sm dark:border-slate-800/60 dark:bg-slate-900/50">
        <div class="text-sm font-medium text-slate-500 dark:text-slate-400">开放邀请</div>
        <div class="relative z-10 mt-2 text-3xl font-bold text-blue-600 dark:text-blue-400">{{ stats.openInvite }}</div>
        <Ticket class="absolute -bottom-3 -right-3 h-16 w-16 text-blue-500 opacity-10 dark:text-blue-400 dark:opacity-10" />
      </div>
      <div class="relative overflow-hidden rounded-2xl border border-slate-200/60 bg-white p-5 shadow-sm dark:border-slate-800/60 dark:bg-slate-900/50">
        <div class="text-sm font-medium text-slate-500 dark:text-slate-400">异常站点</div>
        <div class="relative z-10 mt-2 text-3xl font-bold text-rose-600 dark:text-rose-400">{{ stats.unreachable }}</div>
        <AlertTriangle class="absolute -bottom-3 -right-3 h-16 w-16 text-rose-500 opacity-10 dark:text-rose-400 dark:opacity-10" />
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

    <EmptyState v-if="!loading && !hasRows" title="暂无扫描数据" description="请先在“站点管理”配置或导入站点，然后点击“立即扫描”。" actionText="去配置站点" @action="$router.push('/sites')" />

    <div
      v-else
      class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div class="border-b border-slate-100 px-4 py-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        <span v-if="loading && !hasRows">加载中…</span>
        <span v-else>共 {{ rows.length }} 个站点</span>
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

      <!-- Mobile: Card View -->
      <div v-if="hasRows" class="md:hidden space-y-3">
          <TransitionGroup name="list">
             <SiteCard 
               v-for="(row, index) in sortedRows" 
               :key="row.domain" 
               :site="row" 
               :style="{ '--i': index }"
               @click="selectedSite = row"
             />
          </TransitionGroup>
      </div>

      <!-- Desktop: Table View -->
      <div v-if="hasRows || (!loading && !hasRows)" class="hidden md:block overflow-x-auto max-h-[calc(100vh-300px)]">
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
             <TransitionGroup name="list" appear>
              <tr v-for="(row, index) in sortedRows" :key="row.domain" :style="{ '--i': index }" class="group table-row-hover transition-colors duration-150 hover:bg-slate-50/80 dark:hover:bg-slate-800/30">
              <!-- Site & Domain Combined -->
              <td class="px-6 py-4">
                <div class="flex items-center gap-3">
                  <div class="h-10 w-10">
                    <SiteIcon :url="row.url" :name="row.name || '-'" />
                  </div>
                  <div class="flex flex-col">
                    <span 
                      class="cursor-pointer font-semibold text-slate-700 transition-colors hover:text-brand-600 dark:text-slate-200 dark:hover:text-brand-400"
                      @click="selectedSite = row"
                    >{{ row.name || "-" }}</span>
                    <a class="mt-0.5 text-xs text-brand-500 hover:text-brand-600 hover:underline dark:text-brand-400 dark:hover:text-brand-300" :href="row.url" target="_blank" rel="noreferrer" @click.stop>
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
                    :disabled="scanRunning || loading || scanningDomains.has(row.domain) || row.scanning"
                    @click="runRowScan(row)"
                    title="扫描此站"
                  >
                     <Loader2 v-if="scanningDomains.has(row.domain) || row.scanning" class="h-4 w-4 animate-spin opacity-50" />
                     <RefreshCw v-else class="h-4 w-4" />
                  </button>
                  <button
                     v-if="row.errors && row.errors.length"
                     class="rounded-lg p-2 text-danger-500 transition-colors hover:bg-danger-50 hover:text-danger-600 dark:hover:bg-danger-900/20"
                     @click="openErrors(row)"
                     :title="`查看错误 (${row.errors.length})`"
                  >
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

    <!-- Modals -->
    <Modal :open="showResetConfirm" title="确认重置状态？" @close="showResetConfirm = false">
      <div class="space-y-4">
        <p class="text-sm text-slate-600 dark:text-slate-300">这将清空所有站点的扫描状态（Last Checked, Reachability, Registration/Invite State）。站点配置和 Cookie 将保留。</p>
        <div class="flex justify-end gap-3">
          <Button @click="showResetConfirm = false">取消</Button>
          <Button variant="danger" :loading="resetting" @click="confirmReset">确认重置</Button>
        </div>
      </div>
    </Modal>

    <SiteDetailModal 
      :open="!!selectedSite" 
      :site="selectedSite" 
      @close="selectedSite = null" 
    />

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
