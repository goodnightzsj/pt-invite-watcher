<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import Badge from "../components/Badge.vue";
import Modal from "../components/Modal.vue";
import Button from "../components/Button.vue";
import EmptyState from "../components/EmptyState.vue";
import Card from "../components/Card.vue";
import PageHeader from "../components/PageHeader.vue";
	import FormSelect from "../components/FormSelect.vue";
	import { api, type LogItem } from "../api";
	import { showToast } from "../toast";
	import { WS_LOGS_APPEND, WS_LOGS_UPDATE } from "../ws_events";

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const items = ref<LogItem[]>([]);

// Initial filter/page values read from URL query so reload/deep-link keeps context.
const q0 = route.query as Record<string, string | undefined>;
const category = ref(typeof q0.category === "string" && q0.category ? q0.category : "all");
const domain = ref(typeof q0.domain === "string" ? q0.domain : "");
const keyword = ref(typeof q0.keyword === "string" ? q0.keyword : "");
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

function readStoredPageSize(): number {
  try {
    return parseInt(localStorage.getItem(STORAGE_PAGE_SIZE) || "20", 10);
  } catch {
    return 20;
  }
}

const pageSize = ref(readStoredPageSize());
const initialPage = Number(route.query.page);
const currentPage = ref(Number.isFinite(initialPage) && initialPage > 0 ? initialPage : 1);

function setPageSize(size: number) {
  pageSize.value = size;
  try {
    localStorage.setItem(STORAGE_PAGE_SIZE, String(size));
  } catch {
    /* private mode / quota — ignore */
  }
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
      detailContent.value = JSON.stringify(obj, null, 2).trimStart();
    }
  } catch (e) {
    detailContent.value = String(item.detail || "").trimStart();
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

function formatTime(v: string) {
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, { timeStyle: "medium" }).format(d);
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

// Batched drain via rAF: flush up to MAX_PER_FRAME pending logs per frame, preserving order.
// Only auto-jump to page 1 on the first batch when user is already on page 1 (don't hijack pagination).
let rafHandle: number | undefined;
const MAX_ITEMS = 10000;
const MAX_PER_FRAME = 50;

function drainPendingLogs() {
  rafHandle = undefined;
  if (pendingLogs.value.length === 0) return;
  const batch = pendingLogs.value.splice(0, MAX_PER_FRAME);
  // batch[0] is oldest pending; unshift from oldest->newest so newest ends up at items[0].
  for (const item of batch) {
    items.value.unshift(item);
  }
  if (items.value.length > MAX_ITEMS) {
    items.value.splice(MAX_ITEMS);
  }
  if (pendingLogs.value.length > 0) scheduleDrain();
}

function scheduleDrain() {
  if (rafHandle != null) return;
  rafHandle = window.requestAnimationFrame(drainPendingLogs);
}

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

// Mirror filters + page into the URL so refresh / share preserves context.
// Use replace() so we don't pollute the history stack with every keystroke.
let syncingQuery = false;
function syncQueryToRoute() {
  if (syncingQuery) return;
  syncingQuery = true;
  const q: Record<string, string> = {};
  if (category.value && category.value !== "all") q.category = category.value;
  if (domain.value) q.domain = domain.value;
  if (keyword.value) q.keyword = keyword.value;
  if (currentPage.value > 1) q.page = String(currentPage.value);
  router
    .replace({ query: q })
    .catch(() => { /* NavigationDuplicated is safe to ignore */ })
    .finally(() => { syncingQuery = false; });
}
watch([category, domain, keyword, currentPage], syncQueryToRoute, { flush: "post" });

onMounted(() => {
  loadDomains();
  load();
});

onUnmounted(() => {
  if (rafHandle != null) {
    window.cancelAnimationFrame(rafHandle);
    rafHandle = undefined;
  }
  pendingLogs.value = [];
});

	// WS real-time updates
	import { useWS } from "../ws";
	useWS(WS_LOGS_UPDATE, () => {
	  // refreshing logic if needed, or just reload
	  // load(); // usually logs_update means "clear" or big change, maybe reload?
	  // Current logic was: load()
	  load();
	});

	useWS(WS_LOGS_APPEND, (evt: any) => {
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

  // Buffer the log; drain on next animation frame (batched) to avoid reactive storm.
  pendingLogs.value.push(evt);
  scheduleDrain();
});
</script>

<template>
  <div class="space-y-5">
    <PageHeader title="日志" description="查看扫描、站点、通知、配置等关键事件">
      <template #actions>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div class="flex w-full gap-2 sm:w-auto">
            <div class="w-full min-w-[110px] sm:w-auto">
              <FormSelect v-model="category" :disabled="loading" :options="[
                { label: '全部分类', value: 'all' },
                { label: '扫描相关', value: 'scan' },
                { label: '租约相关', value: 'lease' },
                { label: '站点相关', value: 'site' },
                { label: '通知相关', value: 'notify' },
                { label: '配置相关', value: 'config' },
                { label: '导入导出', value: 'backup' },
              ]" @update:modelValue="load()" />
            </div>
            <div class="w-full min-w-[130px] sm:w-auto">
              <FormSelect v-model="domain" :disabled="loading"
                :options="[{ label: '全部站点', value: '' }, ...domainOptions.map((d) => ({ label: d, value: d }))]"
                @update:modelValue="load()" />
            </div>
          </div>
          <input v-model="keyword" class="ui-input w-full sm:w-60" placeholder="搜索..." :disabled="loading"
            @keyup.enter="load({ toast: true })" />
          <Button :disabled="loading" :loading="loading" @click="reload">刷新</Button>
        </div>
      </template>
    </PageHeader>

    <EmptyState v-if="!hasItems && !loading" title="暂无日志" description="当前没有符合查询条件的日志记录" actionText="刷新"
      @action="reload" />
    <EmptyState v-else-if="loading && !hasItems" title="加载中" description="正在获取日志数据...">
      <template #icon>
        <div
          class="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-brand-500 dark:border-slate-800 dark:border-t-brand-500" />
      </template>
    </EmptyState>

    <Card v-else padding="none" :hoverable="false">
      <div class="overflow-hidden rounded-2xl">
        <div class="overflow-y-auto overflow-x-auto h-[calc(100vh-250px)] relative scroll-smooth">
          <!-- Mobile View -->
          <div class="md:hidden p-4 space-y-3">
            <div v-for="item in paginatedItems" :key="item.id"
              class="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50/50 p-4 active:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/30 dark:active:bg-slate-800"
              style="content-visibility: auto; contain-intrinsic-size: 0 160px;"
              @click="openDetail(item)">
              <div class="flex items-start justify-between gap-2">
                <div class="flex flex-col gap-1">
                  <div class="flex items-center gap-2">
                    <Badge :label="item.level" :tone="toneForLevel(item.level) as any" />
                    <span class="font-mono text-xs text-slate-400 dark:text-slate-400">{{ formatTime(item.ts) }}</span>
                  </div>
                  <div class="text-sm font-medium text-slate-800 dark:text-slate-100 break-all line-clamp-2">
                    {{ item.message }}
                  </div>
                </div>
              </div>

              <div
                class="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 text-xs dark:border-slate-800">
                <span class="text-slate-500">{{ getLocalizedAction(item.action) }}</span>
                <div class="h-3 w-px bg-slate-200 dark:bg-slate-700"></div>
                <span v-if="domainLabel(item) !== '-'" class="text-slate-600 dark:text-slate-300">{{ domainLabel(item)
                  }}</span>
                <span v-if="pageLabel(item)"
                  class="rounded bg-slate-200/50 px-1.5 py-0.5 text-[10px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">{{
                    pageLabel(item) }}</span>
                <Badge :label="item.category" :tone="toneForCategory(item.category) as any" class="ml-auto" />
              </div>
            </div>
          </div>

          <!-- Desktop View -->
          <table class="hidden md:table min-w-full text-left text-sm relative border-collapse">
            <thead
              class="sticky top-0 z-10 border-b border-white/10 bg-white/40 text-xs font-semibold uppercase tracking-wider text-slate-500 backdrop-blur-xl dark:border-white/5 dark:bg-slate-900/40 dark:text-slate-300">
              <tr>
                <th class="px-6 py-4">时间</th>
                <th class="px-6 py-4">分类</th>
                <th class="px-6 py-4">级别</th>
                <th class="px-6 py-4">站点 / 页面</th>
                <th class="px-6 py-4">内容</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800/40">
              <TransitionGroup name="list">
                <tr v-for="item in paginatedItems" :key="item.id"
                  class="table-row-hover group cursor-pointer transition-colors duration-150 hover:bg-slate-50/80 dark:hover:bg-slate-800/30"
                  style="content-visibility: auto; contain-intrinsic-size: 0 64px;"
                  @click="openDetail(item)" :title="item.detail ? '点击查看详情' : ''">
                  <td class="px-6 py-4 text-xs text-slate-500 dark:text-slate-300 font-mono">{{ formatDateTime(item.ts)
                    }}
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
                        class="inline-flex rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-300 w-fit">
                        {{ pageLabel(item) }}
                      </span>
                      <span v-if="domainLabel(item) === '-' && !pageLabel(item)">-</span>
                    </div>
                  </td>
                  <td class="px-6 py-4">
                    <div class="text-sm font-medium text-slate-800 dark:text-slate-100">
                      {{ item.message }}
                    </div>
                    <div class="mt-0.5 text-xs text-slate-500 dark:text-slate-300">
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
          <div class="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-300">
            <span>每页</span>
            <div class="w-[88px]">
              <FormSelect v-model="pageSize" dense
                :options="pageSizeOptions.map((opt) => ({ label: String(opt), value: opt }))"
                @update:modelValue="(v) => setPageSize(v as any)" />
            </div>
            <span>条，第 {{ currentPage }}/{{ totalPages }} 页，共 {{ items.length }} 条</span>
          </div>
          <div class="flex gap-2">
            <button
              class="flex items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-1.5 text-sm font-medium text-slate-700 transition-all hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-200 dark:hover:bg-slate-800"
              :disabled="currentPage <= 1" @click="prevPage">
              上一页
            </button>
            <button
              class="flex items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-1.5 text-sm font-medium text-slate-700 transition-all hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-200 dark:hover:bg-slate-800"
              :disabled="currentPage >= totalPages" @click="nextPage">
              下一页
            </button>
          </div>
        </div>
      </div>
    </Card>

    <Modal :open="showDetail" :title="detailTitle" @close="showDetail = false">
      <div v-if="!detailContent" class="text-sm text-slate-500 dark:text-slate-300">无详情</div>
      <pre
        v-else
        v-text="detailContent"
        class="whitespace-pre-wrap break-words rounded-xl border border-slate-200 bg-slate-50 py-3 pr-3 pl-0 text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-200"
      ></pre>
    </Modal>
  </div>
</template>
