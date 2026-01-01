<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import Badge from "../components/Badge.vue";
import Modal from "../components/Modal.vue";
import Button from "../components/Button.vue";
import EmptyState from "../components/EmptyState.vue";
import Card from "../components/Card.vue";
import { api, type LogItem } from "../api";
import { showToast } from "../toast";

const loading = ref(false);
const items = ref<LogItem[]>([]);

const category = ref("all");
const domain = ref("");  // New: site filter
const keyword = ref("");
const limit = ref(0); // 0 means unlimited
const pendingLogs = ref<LogItem[]>([]);


// Site domains list for filter dropdown
const domainOptions = ref<string[]>([]);

async function loadDomains() {
  try {
    const resp = await api.logsDomains();
    domainOptions.value = (resp.domains || []).sort();
  } catch (e) {
    // Ignore errors, dropdown will just be empty
  }
}

// Pagination
const STORAGE_PAGE_SIZE = "ptiw_logs_page_size";
const pageSizeOptions = [10, 20, 50, 100];
const pageSize = ref(parseInt(localStorage.getItem(STORAGE_PAGE_SIZE) || "20", 10));
const currentPage = ref(1);

function setPageSize(size: number) {
  pageSize.value = size;
  localStorage.setItem(STORAGE_PAGE_SIZE, String(size));
  resetPage();
}

const showDetail = ref(false);
const detailTitle = ref("");
const detailContent = ref<any>(null);

function openDetail(item: LogItem) {
  detailContent.value = "";
  try {
    if (item.detail) {
      const obj = typeof item.detail === 'string' ? JSON.parse(item.detail) : item.detail;
      detailContent.value = JSON.stringify(obj, null, 2);
    }
  } catch (e) {
    detailContent.value = String(item.detail);
  }
  detailTitle.value = `详情 - ${getLocalizedAction(item.action)}`;
  showDetail.value = true;
}

function toneForLevel(level: string) {
  const v = (level || "").toLowerCase();
  if (v === "error") return "red";
  if (v === "warn" || v === "warning") return "amber";
  return "green";
}

function toneForCategory(cat: string) {
  const v = (cat || "").toLowerCase();
  if (v === "scan") return "slate";
  if (v === "site") return "amber";
  if (v === "notify") return "green";
  if (v === "config") return "slate";
  if (v === "backup") return "slate";
  return "slate";
}

function formatDateTime(v: string) {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" }).format(d);
}

// Action localization map
const actionMap: Record<string, string> = {
  "check_reachability": "检测连通性",
  "check_registration": "检测注册",
  "check_invites": "检测邀请",
  "check_invites_mteam": "检测邀请 (M-Team)",
  "state_changed": "状态变更",
  "site_unreachable": "站点不可达",
  "scan_start": "开始扫描",
  "scan_done": "扫描完成",
  "scan_skipped": "跳过扫描",
  "scan_failed": "扫描失败",
  "scan_one_start": "开始单独扫描",
  "scan_one_done": "单独扫描完成",
  "scan_one_not_found": "站点未找到",
  "scan_one_failed": "单独扫描失败",
  "skip_invites": "跳过邀请检测",
  "site_list_changed": "站点列表变更"
};

function getLocalizedAction(action: string) {
  return actionMap[action] || action;
}

// Flush pending logs every 300ms to prevent UI stuttering
setInterval(() => {
  if (pendingLogs.value.length > 0) {
    // Determine strict filtering active state (consistent with useWS logic)
    // Note: We already filter before pushing to pendingLogs, so just dump here.
    // However, if filters CHANGED while logs were pending, we might show wrong logs.
    // But 300ms is short, accept minor race or re-filter?
    // Let's filtered push to pending, so here we just unshift.

    // Reverse to keep order: we want newest at top. 
    // WebSocket gives us streaming events. We pushed them to pendingLogs as they came (End or Start?).
    // Usually we unshift to top. So later events should be at index 0 of table.
    // If pendingLogs has [OldestPending, ..., NewestPending], we should reverse insert?
    // Actually standard appending: pendingLogs.push(evt).
    // So pendingLogs[0] is OldestPending.
    // We want items = [NewestPending, ..., OldestPending, ...OldItems]
    // So we need to reverse pendingLogs and unshift.

    const batch = [...pendingLogs.value].reverse();
    items.value.unshift(...batch);
    pendingLogs.value = [];

    // Safety cap 10k
    if (items.value.length > 10000) {
      items.value.splice(10000);
    }
  }
}, 300);

async function load(opts: { toast?: boolean } = {}) {
  loading.value = true;
  try {
    const resp = await api.logsList({
      category: category.value,
      domain: domain.value,
      keyword: keyword.value,
      limit: limit.value,
    });
    items.value = resp.items || [];
    resetPage();
    if (opts.toast) showToast("日志已刷新", "success", 1800);
  } catch (e: any) {
    showToast(String(e?.message || e || "加载失败"), "error", 4500);
  } finally {
    loading.value = false;
  }
}

async function reload() {
  if (loading.value) return;
  showToast("正在刷新日志…", "info", 1400);
  await load({ toast: true });
}


function domainLabel(item: LogItem) {
  if (item.category === "scan" && !item.domain && ["scan_start", "scan_done", "scan_skipped", "scan_failed"].includes(item.action)) {
    return "全部站点";
  }
  return item.domain || "-";
}

function pageLabel(item: LogItem) {
  const p = item.detail?.page;
  if (!p || !p.kind) return "";
  const map: Record<string, string> = {
    home: "首页",
    usercp: "个人中心",
    signup: "注册页",
    userdetail: "用户详情",
    invite: "邀请页",
    login: "登录页"
  };
  return map[p.kind] || p.kind;
}

const hasItems = computed(() => items.value.length > 0);

// Pagination computed
const totalPages = computed(() => Math.ceil(items.value.length / pageSize.value) || 1);
const paginatedItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return items.value.slice(start, start + pageSize.value);
});

function prevPage() {
  if (currentPage.value > 1) currentPage.value--;
}
function nextPage() {
  if (currentPage.value < totalPages.value) currentPage.value++;
}
function resetPage() {
  currentPage.value = 1;
}

onMounted(() => {
  loadDomains();
  load();
});

// WS real-time updates
import { useWS } from "../ws";
useWS("logs_update", () => {
  // refreshing logic if needed, or just reload
  // load(); // usually logs_update means "clear" or big change, maybe reload?
  // Current logic was: load()
  load();
});

useWS("logs_append", (evt: any) => {
  if (!evt || !evt.id) return;
  // Strict Filter check
  const cat = category.value;
  // If specific category selected, mismatched category -> skip
  if (cat !== "all" && evt.category !== cat) return;

  const dom = domain.value;
  // If specific domain selected, mismatched domain -> skip (strict equality, normalized)
  // Backend domain is already lowercase.
  if (dom && evt.domain !== dom) return;

  const kw = keyword.value.trim().toLowerCase();
  if (kw) {
    const txt = (evt.message + (evt.action || "") + (evt.domain || "")).toLowerCase();
    if (!txt.includes(kw)) return;
  }

  // Buffer the log instead of direct unshift
  pendingLogs.value.push(evt);
});
</script>

<template>
  <div class="space-y-5">
    <div
      class="rounded-3xl border border-slate-200/60 bg-white p-6 shadow-sm shadow-slate-200/50 dark:border-slate-800/60 dark:bg-slate-900/50 dark:shadow-none">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div class="flex items-center gap-2">
            <div class="h-2 w-2 rounded-full bg-brand-500 ring-2 ring-brand-100 dark:ring-brand-900"></div>
            <h2 class="text-lg font-bold text-slate-900 dark:text-white">日志</h2>
          </div>
          <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">查看扫描、站点、通知、配置等关键事件</p>
        </div>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div class="flex w-full gap-2 sm:w-auto">
            <select v-model="category" class="ui-select w-full min-w-[110px] sm:w-auto" :disabled="loading"
              @change="load()">
              <option value="all">全部分类</option>
              <option value="scan">扫描相关</option>
              <option value="site">站点相关</option>
              <option value="notify">通知相关</option>
              <option value="config">配置相关</option>
              <option value="backup">导入导出</option>
            </select>
            <select v-model="domain" class="ui-select w-full min-w-[130px] sm:w-auto" :disabled="loading"
              @change="load()">
              <option value="">全部站点</option>
              <option v-for="d in domainOptions" :key="d" :value="d">{{ d }}</option>
            </select>
          </div>
          <input v-model="keyword" class="ui-input w-full sm:w-60" placeholder="搜索..." :disabled="loading"
            @keyup.enter="load({ toast: true })" />
        </div>
      </div>
    </div>

    <EmptyState v-if="!hasItems && !loading" title="暂无日志" description="当前没有符合查询条件的日志记录" actionText="刷新"
      @action="reload" />
    <EmptyState v-else-if="loading && !hasItems" title="加载中" description="正在获取日志数据...">
      <template #icon>
        <div
          class="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-brand-500 dark:border-slate-800 dark:border-t-brand-500" />
      </template>
    </EmptyState>

    <div v-else
      class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="overflow-y-auto overflow-x-auto h-[calc(100vh-250px)] relative">
        <table class="min-w-full text-left text-sm relative border-collapse">
          <thead
            class="sticky top-0 z-10 border-b border-slate-200/70 bg-slate-50 text-xs uppercase tracking-wider text-slate-500 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
            <tr>
              <th class="px-6 py-4 font-semibold">时间</th>
              <th class="px-6 py-4 font-semibold">分类</th>
              <th class="px-6 py-4 font-semibold">级别</th>
              <th class="px-6 py-4 font-semibold">站点 / 页面</th>
              <th class="px-6 py-4 font-semibold">内容</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800/60">
            <TransitionGroup name="list">
              <tr v-for="item in paginatedItems" :key="item.id"
                class="table-row-hover group cursor-pointer transition-colors duration-150 hover:bg-slate-50/80 dark:hover:bg-slate-800/30"
                @click="openDetail(item)" :title="item.detail ? '点击查看详情' : ''">
                <td class="px-6 py-4 text-xs text-slate-500 dark:text-slate-400 font-mono">{{ formatDateTime(item.ts) }}
                </td>
                <td class="px-6 py-4">
                  <Badge :label="item.category" :tone="toneForCategory(item.category) as any" />
                </td>
                <td class="px-6 py-4">
                  <Badge :label="item.level" :tone="toneForLevel(item.level) as any" />
                </td>
                <td class="px-6 py-4 text-xs text-slate-600 dark:text-slate-300">
                  <div class="flex flex-col gap-1">
                    <span v-if="domainLabel(item) !== '-'">{{ domainLabel(item) }}</span>
                    <span v-if="pageLabel(item)"
                      class="inline-flex rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400 w-fit">
                      {{ pageLabel(item) }}
                    </span>
                    <span v-if="domainLabel(item) === '-' && !pageLabel(item)">-</span>
                  </div>
                </td>
                <td class="px-6 py-4">
                  <div class="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {{ item.message }}
                  </div>
                  <div class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                    {{ item.action }}
                  </div>
                </td>
              </tr>
            </TransitionGroup>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1 || items.length > 10"
        class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3 dark:border-slate-800">
        <div class="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
          <span>每页</span>
          <select v-model.number="pageSize" class="ui-select w-auto py-1 text-sm" @change="setPageSize(pageSize)">
            <option v-for="opt in pageSizeOptions" :key="opt" :value="opt">{{ opt }}</option>
          </select>
          <span>条，第 {{ currentPage }}/{{ totalPages }} 页，共 {{ items.length }} 条</span>
        </div>
        <div class="flex gap-2">
          <button
            class="whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-40 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
            :disabled="currentPage <= 1" @click="prevPage">
            上一页
          </button>
          <button
            class="whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-40 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
            :disabled="currentPage >= totalPages" @click="nextPage">
            下一页
          </button>
        </div>
      </div>
    </div>

    <Modal :open="showDetail" :title="detailTitle" @close="showDetail = false">
      <div v-if="!detailContent" class="text-sm text-slate-500 dark:text-slate-400">无详情</div>
      <pre v-else
        class="whitespace-pre-wrap break-words rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
    {{ detailContent }}</pre>
    </Modal>
  </div>
</template>
