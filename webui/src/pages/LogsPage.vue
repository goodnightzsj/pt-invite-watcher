<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import Badge from "../components/Badge.vue";
import Modal from "../components/Modal.vue";
import { api, type LogItem } from "../api";
import { showToast } from "../toast";

const loading = ref(false);
const items = ref<LogItem[]>([]);

const category = ref("all");
const keyword = ref("");
const limit = ref(200);

const modalOpen = ref(false);
const modalTitle = ref("");
const modalDetail = ref<any>(null);

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

async function load(opts: { toast?: boolean } = {}) {
  loading.value = true;
  try {
    const resp = await api.logsList({ category: category.value, keyword: keyword.value, limit: limit.value });
    items.value = resp.items || [];
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

async function clear() {
  if (loading.value) return;
  if (!confirm("确认清空日志吗？")) return;
  loading.value = true;
  try {
    await api.logsClear();
    showToast("日志已清空", "success", 1800);
    await load();
  } catch (e: any) {
    showToast(String(e?.message || e || "清空失败"), "error", 4500);
  } finally {
    loading.value = false;
  }
}

function openDetail(item: LogItem) {
  modalTitle.value = `${item.category}/${item.action}${item.domain ? ` · ${item.domain}` : ""}`;
  modalDetail.value = item.detail;
  modalOpen.value = true;
}

function domainLabel(item: LogItem) {
  const dom = String(item?.domain || "").trim();
  if (dom) return dom;
  const cat = String(item?.category || "").toLowerCase();
  if (cat === "scan") return "全部";
  return "-";
}

const hasItems = computed(() => items.value.length > 0);

onMounted(() => load());
</script>

<template>
  <div class="space-y-5">
    <div class="rounded-3xl border border-slate-200/60 bg-white p-6 shadow-sm shadow-slate-200/50 dark:border-slate-800/60 dark:bg-slate-900/50 dark:shadow-none">
      <div class="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div class="flex items-center gap-2">
            <div class="h-2 w-2 rounded-full bg-indigo-500 ring-2 ring-indigo-100 dark:ring-indigo-900"></div>
            <h2 class="text-lg font-bold text-slate-900 dark:text-white">日志</h2>
          </div>
          <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">查看扫描、站点、通知、配置等关键事件</p>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <select v-model="category" class="ui-select w-auto" :disabled="loading" @change="load()">
            <option value="all">全部</option>
            <option value="scan">扫描相关</option>
            <option value="site">站点相关</option>
            <option value="notify">通知相关</option>
            <option value="config">配置相关</option>
            <option value="backup">导入导出</option>
          </select>
          <input
            v-model="keyword"
            class="ui-input w-56"
            placeholder="搜索关键字/域名"
            :disabled="loading"
            @keyup.enter="load({ toast: true })"
          />
          <button
            class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            :disabled="loading"
            @click="reload"
          >
            刷新
          </button>
          <button
            class="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300 dark:hover:bg-rose-900/50"
            :disabled="loading"
            @click="clear"
          >
            清空
          </button>
        </div>
      </div>
    </div>

    <div v-if="!hasItems" class="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
      暂无日志
    </div>

    <div v-else class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="overflow-x-auto">
        <table class="min-w-full text-left text-sm">
          <thead class="border-b border-slate-200/70 bg-slate-50 text-xs uppercase tracking-wider text-slate-500 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-400">
            <tr>
              <th class="px-6 py-4 font-semibold">时间</th>
              <th class="px-6 py-4 font-semibold">分类</th>
              <th class="px-6 py-4 font-semibold">级别</th>
              <th class="px-6 py-4 font-semibold">站点</th>
              <th class="px-6 py-4 font-semibold">内容</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800/60">
            <tr
              v-for="item in items"
              :key="item.id"
              class="group cursor-pointer transition-colors duration-150 hover:bg-slate-50/80 dark:hover:bg-slate-800/30"
              @click="openDetail(item)"
              :title="item.detail ? '点击查看详情' : ''"
            >
              <td class="px-6 py-4 text-xs text-slate-500 dark:text-slate-400">{{ formatDateTime(item.ts) }}</td>
              <td class="px-6 py-4">
                <Badge :label="item.category" :tone="toneForCategory(item.category) as any" />
              </td>
              <td class="px-6 py-4">
                <Badge :label="item.level" :tone="toneForLevel(item.level) as any" />
              </td>
              <td class="px-6 py-4 text-xs text-slate-600 dark:text-slate-300">
                {{ domainLabel(item) }}
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
          </tbody>
        </table>
      </div>
    </div>

    <Modal :open="modalOpen" :title="modalTitle" @close="modalOpen = false">
      <div v-if="!modalDetail" class="text-sm text-slate-500 dark:text-slate-400">无详情</div>
      <pre v-else class="whitespace-pre-wrap break-words rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-200">{{
        JSON.stringify(modalDetail, null, 2)
      }}</pre>
    </Modal>
  </div>
</template>
