<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import Badge from "../components/Badge.vue";
import Toggle from "../components/Toggle.vue";
import { api, type ConfigResponse } from "../api";
import { showToast } from "../toast";

const STORAGE_REFRESH_ENABLED = "ptiw_auto_refresh_enabled";
const STORAGE_REFRESH_MINUTES = "ptiw_auto_refresh_minutes";

type Model = {
  moviepilot: { base_url: string; username: string; password: string; otp_password: string; sites_cache_ttl_seconds: number };
  connectivity: { retry_interval_seconds: number; request_retry_delay_seconds: number };
  cookie: { source: string; cookiecloud: { base_url: string; uuid: string; password: string; refresh_interval_seconds: number } };
  scan: { interval_seconds: number; timeout_seconds: number; concurrency: number; user_agent: string; trust_env: boolean };
  ui: { allow_state_reset: boolean };
};

const loading = ref(false);
const saving = ref(false);
const backupBusy = ref(false);
const scanNowRunning = ref(false);
const importScanPrompt = ref(false);
const view = ref<ConfigResponse | null>(null);
const baselineJson = ref<string>("");
const model = reactive<Model>({
  moviepilot: { base_url: "", username: "", password: "", otp_password: "", sites_cache_ttl_seconds: 86400 },
  connectivity: { retry_interval_seconds: 3600, request_retry_delay_seconds: 30 },
  cookie: { source: "auto", cookiecloud: { base_url: "", uuid: "", password: "", refresh_interval_seconds: 300 } },
  scan: { interval_seconds: 600, timeout_seconds: 20, concurrency: 8, user_agent: "", trust_env: false },
  ui: { allow_state_reset: true },
});

function _normStr(v: string) {
  return (v || "").trim();
}

function normalizedModelForCompare(m: Model) {
  return {
    moviepilot: {
      base_url: _normStr(m.moviepilot.base_url),
      username: _normStr(m.moviepilot.username),
      password: _normStr(m.moviepilot.password),
      otp_password: _normStr(m.moviepilot.otp_password),
      sites_cache_ttl_seconds: Number(m.moviepilot.sites_cache_ttl_seconds || 0),
    },
    connectivity: {
      retry_interval_seconds: Number(m.connectivity.retry_interval_seconds || 0),
      request_retry_delay_seconds: Number(m.connectivity.request_retry_delay_seconds || 0),
    },
    cookie: {
      source: _normStr(m.cookie.source),
      cookiecloud: {
        base_url: _normStr(m.cookie.cookiecloud.base_url),
        uuid: _normStr(m.cookie.cookiecloud.uuid),
        password: _normStr(m.cookie.cookiecloud.password),
        refresh_interval_seconds: Number(m.cookie.cookiecloud.refresh_interval_seconds || 0),
      },
    },
    scan: {
      interval_seconds: Number(m.scan.interval_seconds || 0),
      timeout_seconds: Number(m.scan.timeout_seconds || 0),
      concurrency: Number(m.scan.concurrency || 0),
      user_agent: _normStr(m.scan.user_agent),
      trust_env: Boolean(m.scan.trust_env),
    },
    ui: {
      allow_state_reset: Boolean(m.ui.allow_state_reset),
    },
  };
}

const isDirty = computed(() => {
  if (!baselineJson.value) return false;
  const current = JSON.stringify(normalizedModelForCompare(model));
  return current !== baselineJson.value;
});

async function load(opts: { toast?: boolean } = {}) {
  loading.value = true;
  try {
    const data = await api.configGet();
    view.value = data;
    model.moviepilot.base_url = data.moviepilot.base_url || "";
    model.moviepilot.username = data.moviepilot.username || "";
    model.moviepilot.password = "";
    model.moviepilot.otp_password = "";
    model.moviepilot.sites_cache_ttl_seconds = data.moviepilot.sites_cache_ttl_seconds || 86400;
    model.connectivity.retry_interval_seconds = data.connectivity?.retry_interval_seconds || 3600;
    model.connectivity.request_retry_delay_seconds = data.connectivity?.request_retry_delay_seconds ?? 30;

    model.cookie.source = data.cookie.source || "auto";
    model.cookie.cookiecloud.base_url = data.cookie.cookiecloud.base_url || "";
    model.cookie.cookiecloud.uuid = data.cookie.cookiecloud.uuid || "";
    model.cookie.cookiecloud.password = "";
    model.cookie.cookiecloud.refresh_interval_seconds = data.cookie.cookiecloud.refresh_interval_seconds || 300;

    model.scan.interval_seconds = data.scan.interval_seconds || 600;
    model.scan.timeout_seconds = data.scan.timeout_seconds || 20;
    model.scan.concurrency = data.scan.concurrency || 8;
    model.scan.user_agent = data.scan.user_agent || "";
    model.scan.trust_env = !!data.scan.trust_env;
    model.ui.allow_state_reset = data.ui?.allow_state_reset ?? true;

    baselineJson.value = JSON.stringify(normalizedModelForCompare(model));
    if (opts.toast) showToast("已重新加载", "success", 1800);
  } catch (e: any) {
    showToast(String(e?.message || e || "加载失败"), "error");
  } finally {
    loading.value = false;
  }
}

async function reload() {
  if (loading.value) return;
  showToast("正在重新加载…", "info", 1600);
  await load({ toast: true });
}

async function save() {
  saving.value = true;
  try {
    showToast("正在保存…", "info", 1600);
    const payload: any = {
      moviepilot: {
        base_url: model.moviepilot.base_url,
        username: model.moviepilot.username,
        sites_cache_ttl_seconds: model.moviepilot.sites_cache_ttl_seconds,
      },
      connectivity: {
        retry_interval_seconds: model.connectivity.retry_interval_seconds,
        request_retry_delay_seconds: model.connectivity.request_retry_delay_seconds,
      },
      cookie: {
        source: model.cookie.source,
        cookiecloud: {
          base_url: model.cookie.cookiecloud.base_url,
          uuid: model.cookie.cookiecloud.uuid,
          refresh_interval_seconds: model.cookie.cookiecloud.refresh_interval_seconds,
        },
      },
      scan: {
        interval_seconds: model.scan.interval_seconds,
        timeout_seconds: model.scan.timeout_seconds,
        concurrency: model.scan.concurrency,
        user_agent: model.scan.user_agent,
        trust_env: model.scan.trust_env,
      },
      ui: {
        allow_state_reset: model.ui.allow_state_reset,
      },
    };

    if (model.moviepilot.password.trim()) payload.moviepilot.password = model.moviepilot.password.trim();
    if (model.moviepilot.otp_password.trim()) payload.moviepilot.otp_password = model.moviepilot.otp_password.trim();
    if (model.cookie.cookiecloud.password.trim()) payload.cookie.cookiecloud.password = model.cookie.cookiecloud.password.trim();

    await api.configPut(payload);
    showToast("已保存（下一轮扫描生效）", "success");
    await load();
  } catch (e: any) {
    showToast(String(e?.message || e || "保存失败"), "error");
  } finally {
    saving.value = false;
  }
}

async function resetAll() {
  if (!confirm("确认清空 Web UI 配置并回退到 config.yaml/env 吗？")) return;
  try {
    showToast("正在重置…", "info", 1600);
    await api.configReset();
    showToast("已重置", "success");
    await load();
  } catch (e: any) {
    showToast(String(e?.message || e || "重置失败"), "error");
  }
}

function _downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function _backupFilename() {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `pt-invite-watcher-backup-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(
    d.getSeconds()
  )}.json`;
}

function _readAutoRefreshPrefs() {
  const enabled = localStorage.getItem(STORAGE_REFRESH_ENABLED) === "1";
  const minutes = Number(localStorage.getItem(STORAGE_REFRESH_MINUTES) || "10");
  return { enabled, minutes: Number.isFinite(minutes) ? minutes : 10 };
}

function _applyAutoRefreshPrefs(prefs: any) {
  const enabled = !!prefs?.enabled;
  const minutes = Number(prefs?.minutes ?? 10);
  localStorage.setItem(STORAGE_REFRESH_ENABLED, enabled ? "1" : "0");
  if (Number.isFinite(minutes) && minutes > 0) {
    localStorage.setItem(STORAGE_REFRESH_MINUTES, String(Math.round(minutes)));
  }
}

async function exportBackup(includeSecrets: boolean) {
  if (backupBusy.value) return;
  backupBusy.value = true;
  try {
    showToast("正在导出…", "info", 1600);
    const backup = await api.backupExport(includeSecrets);
    const uiPrefs = _readAutoRefreshPrefs();
    const payload = {
      ...backup,
      ui: {
        auto_refresh: uiPrefs,
      },
    };
    _downloadJson(_backupFilename(), payload);
    showToast(includeSecrets ? "已导出（含敏感信息）" : "已导出（脱敏）", "success", 2200);
  } catch (e: any) {
    showToast(String(e?.message || e || "导出失败"), "error", 4500);
  } finally {
    backupBusy.value = false;
  }
}

async function runScanNow() {
  if (scanNowRunning.value) return;
  scanNowRunning.value = true;
  try {
    showToast("开始扫描…", "info", 1600);
    const status = await api.scanRun();
    showToast(status?.ok ? "扫描已完成" : `扫描失败：${status?.error || "unknown"}`, status?.ok ? "success" : "error", status?.ok ? 2200 : 4500);
  } catch (e: any) {
    showToast(String(e?.message || e || "扫描失败"), "error", 4500);
  } finally {
    scanNowRunning.value = false;
  }
}

const importMode = ref<"merge" | "replace">("merge");
const importFile = ref<File | null>(null);

function onPickFile(e: Event) {
  const input = e.target as HTMLInputElement;
  importFile.value = input?.files?.[0] || null;
}

async function importBackup() {
  if (backupBusy.value) return;
  if (!importFile.value) {
    showToast("请选择要导入的 JSON 文件", "error");
    return;
  }
  backupBusy.value = true;
  try {
    showToast("正在导入…", "info", 1600);
    const text = await importFile.value.text();
    const parsed = JSON.parse(text);
    if (parsed?.ui?.auto_refresh) {
      _applyAutoRefreshPrefs(parsed.ui.auto_refresh);
    }
    const res = await api.backupImport(parsed, importMode.value);
    if (res?.ok) {
      importScanPrompt.value = !!res?.needs_scan;
      showToast(res?.needs_scan ? "导入成功：请立即扫描生成站点状态" : "导入成功", "success", 3600);
    } else {
      showToast(`导入失败：${res?.message || "fail"}`, "error", 4500);
    }
    await load();
  } catch (e: any) {
    showToast(String(e?.message || e || "导入失败"), "error", 4500);
  } finally {
    backupBusy.value = false;
  }
}

onMounted(() => load());
</script>

<template>
  <div class="space-y-5">
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-base font-semibold">导入 / 导出</div>
          <div class="mt-1 text-sm text-slate-500 dark:text-slate-400">
            备份本服务 SQLite 中的运行时配置（服务配置 / 通知设置 / 站点管理）；不包含扫描结果与历史。
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <button
            class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            :disabled="backupBusy"
            @click="exportBackup(false)"
          >
            导出（脱敏）
          </button>
          <button
            class="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
            :disabled="backupBusy"
            @click="exportBackup(true)"
          >
            导出（含敏感信息）
          </button>
        </div>
      </div>

      <div class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div class="md:col-span-2">
          <label class="block text-sm font-medium">导入 JSON 文件</label>
          <input
            type="file"
            accept="application/json"
            class="mt-1 block w-full text-sm text-slate-700 file:mr-3 file:rounded-xl file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-slate-800 dark:text-slate-200 dark:file:bg-slate-100 dark:file:text-slate-900 dark:hover:file:bg-white"
            @change="onPickFile"
          />
          <div v-if="importFile" class="mt-1 text-xs text-slate-500 dark:text-slate-400">已选择：{{ importFile.name }}</div>
        </div>
        <div>
          <label class="block text-sm font-medium">导入模式</label>
          <select v-model="importMode" class="mt-1 ui-select">
            <option value="merge">merge（合并，保留本地敏感字段）</option>
            <option value="replace">replace（覆盖，按备份为准）</option>
          </select>
          <button
            class="mt-3 w-full rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            :disabled="backupBusy || !importFile"
            @click="importBackup"
          >
            导入
          </button>
        </div>
      </div>

      <div class="mt-3 text-xs text-slate-500 dark:text-slate-400">
        备份文件会额外包含浏览器本地的“自动刷新开关/间隔”设置；导入后会写入当前浏览器 localStorage。
      </div>

      <div
        v-if="importScanPrompt"
        class="mt-4 rounded-xl border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-900 dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-100"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="font-semibold">下一步</div>
            <div class="mt-1 text-indigo-800/80 dark:text-indigo-200/80">
              导入只恢复站点/通知/服务配置，不包含扫描结果；请点击“立即扫描”生成站点状态。站点管理/通知设置页需要点“重新加载”查看导入结果。
            </div>
          </div>
          <button
            class="inline-flex items-center justify-center rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="scanNowRunning"
            @click="runScanNow"
          >
            {{ scanNowRunning ? "扫描中…" : "立即扫描" }}
          </button>
        </div>
      </div>
    </div>

    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-base font-semibold">服务配置</div>
          <div class="mt-1 text-sm text-slate-500 dark:text-slate-400">
            配置保存在本服务 SQLite，并在下一轮扫描生效。
          </div>
          <div class="mt-1 text-sm text-slate-500 dark:text-slate-400">
            敏感信息会存储在本服务的 SQLite；建议为 Web UI 配置 BasicAuth 或仅在内网使用。
          </div>
        </div>
        <div class="flex items-center gap-3">
          <button
            class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            :disabled="loading"
            @click="reload"
          >
            重新加载
          </button>
          <button
            class="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
            :disabled="saving || !isDirty"
            @click="save"
          >
            保存
          </button>
          <button
            class="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-800 hover:bg-rose-100 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200 dark:hover:bg-rose-950/60"
            @click="resetAll"
          >
            重置
          </button>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="mb-4 flex items-center justify-between">
          <div class="text-sm font-semibold">MoviePilot</div>
          <Badge
            v-if="view"
            :label="view.moviepilot.password_configured ? 'password 已配置' : 'password 未配置'"
            :tone="view.moviepilot.password_configured ? 'green' : 'amber'"
          />
        </div>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium">Base URL</label>
            <input v-model="model.moviepilot.base_url" class="mt-1 ui-input" placeholder="http://192.168.31.122:3010" />
          </div>
          <div>
            <label class="block text-sm font-medium">用户名</label>
            <input v-model="model.moviepilot.username" class="mt-1 ui-input" placeholder="admin" />
          </div>
          <div>
            <label class="block text-sm font-medium">密码（留空不修改）</label>
            <input
              v-model="model.moviepilot.password"
              type="password"
              class="mt-1 ui-input"
              :placeholder="view?.moviepilot.password_configured ? '已配置' : '未配置'"
            />
          </div>
          <div>
            <label class="block text-sm font-medium">OTP 密码（可选，留空不修改）</label>
            <input
              v-model="model.moviepilot.otp_password"
              type="password"
              class="mt-1 ui-input"
              :placeholder="view?.moviepilot.otp_configured ? '已配置' : '未配置'"
            />
          </div>
          <div>
            <label class="block text-sm font-medium">站点列表缓存 TTL（秒）</label>
            <input
              v-model.number="model.moviepilot.sites_cache_ttl_seconds"
              type="number"
              min="60"
              max="604800"
              class="mt-1 ui-input"
            />
            <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">MoviePilot 拉取失败时，未过期缓存可用于继续扫描。</div>
          </div>
        </div>
      </div>

      <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="mb-4 flex items-center justify-between">
          <div class="text-sm font-semibold">Cookie</div>
          <Badge :label="model.cookie.source" tone="slate" />
        </div>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium">Cookie 来源</label>
            <select v-model="model.cookie.source" class="mt-1 ui-select">
              <option value="auto">auto（CookieCloud 优先，失败回退 MoviePilot）</option>
              <option value="cookiecloud">cookiecloud（仅 CookieCloud）</option>
              <option value="moviepilot">moviepilot（仅 MoviePilot）</option>
            </select>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
            <div class="mb-3 text-sm font-semibold">CookieCloud</div>
            <div class="space-y-3">
              <div>
                <label class="block text-sm font-medium">Base URL</label>
                <input v-model="model.cookie.cookiecloud.base_url" class="mt-1 ui-input" placeholder="http://cookiecloud:8088" />
              </div>
              <div>
                <label class="block text-sm font-medium">UUID</label>
                <input v-model="model.cookie.cookiecloud.uuid" class="mt-1 ui-input" placeholder="xxxx" />
              </div>
              <div>
                <label class="block text-sm font-medium">密码（留空不修改）</label>
                <input
                  v-model="model.cookie.cookiecloud.password"
                  type="password"
                  class="mt-1 ui-input"
                  :placeholder="view?.cookie.cookiecloud.password_configured ? '已配置' : '未配置'"
                />
              </div>
              <div>
                <label class="block text-sm font-medium">刷新间隔（秒）</label>
                <input
                  v-model.number="model.cookie.cookiecloud.refresh_interval_seconds"
                  type="number"
                  min="30"
                  max="86400"
                  class="mt-1 ui-input"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="mb-4 flex items-center justify-between">
        <div class="text-sm font-semibold">扫描</div>
        <Badge :label="`interval=${model.scan.interval_seconds}s`" tone="slate" />
      </div>

      <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label class="block text-sm font-medium">间隔（秒，保存后下一轮生效）</label>
          <input v-model.number="model.scan.interval_seconds" type="number" min="30" max="86400" class="mt-1 ui-input" />
        </div>
        <div>
          <label class="block text-sm font-medium">依赖重试间隔（MoviePilot / CookieCloud）</label>
          <select v-model.number="model.connectivity.retry_interval_seconds" class="mt-1 ui-select">
            <option :value="60">1 分钟</option>
            <option :value="300">5 分钟</option>
            <option :value="600">10 分钟</option>
            <option :value="1800">30 分钟</option>
            <option :value="3600">60 分钟</option>
            <option :value="7200">2 小时</option>
            <option :value="21600">6 小时</option>
            <option :value="43200">12 小时</option>
            <option :value="86400">24 小时</option>
          </select>
          <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">
            依赖连接失败时会优先使用缓存，并按此间隔重新尝试恢复连接。
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium">网络请求失败重试延迟（站点探测 / 通知）</label>
          <select v-model.number="model.connectivity.request_retry_delay_seconds" class="mt-1 ui-select">
            <option :value="30">30 秒</option>
            <option :value="60">60 秒</option>
            <option :value="300">5 分钟</option>
            <option :value="600">10 分钟</option>
            <option :value="1800">30 分钟</option>
            <option :value="3600">60 分钟</option>
            <option :value="7200">2 小时</option>
            <option :value="21600">6 小时</option>
            <option :value="43200">12 小时</option>
            <option :value="86400">24 小时</option>
          </select>
          <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">遇到网络异常/5xx/429/408 时会按此间隔重试（最多 3 次）。</div>
        </div>
        <div>
          <label class="block text-sm font-medium">超时（秒）</label>
          <input v-model.number="model.scan.timeout_seconds" type="number" min="5" max="180" class="mt-1 ui-input" />
        </div>
        <div>
          <label class="block text-sm font-medium">并发数</label>
          <input v-model.number="model.scan.concurrency" type="number" min="1" max="64" class="mt-1 ui-input" />
        </div>
        <div>
          <label class="block text-sm font-medium">User-Agent（留空使用默认/站点 UA）</label>
          <input v-model="model.scan.user_agent" type="text" class="mt-1 ui-input" placeholder="Mozilla/5.0 ..." />
        </div>
        <div class="md:col-span-2">
          <div class="flex items-center gap-3">
            <Toggle v-model="model.scan.trust_env" />
            <div class="text-sm text-slate-700 dark:text-slate-200">使用系统代理环境变量（HTTP_PROXY/HTTPS_PROXY/ALL_PROXY）</div>
          </div>
        </div>
      </div>
    </div>

    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="mb-4 flex items-center justify-between">
        <div class="text-sm font-semibold">UI</div>
      </div>
      <div class="flex items-center gap-3">
        <Toggle v-model="model.ui.allow_state_reset" />
        <div class="text-sm text-slate-700 dark:text-slate-200">允许在“站点状态”页显示“重置状态”按钮</div>
      </div>
      <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">用于清空扫描结果（不影响站点配置）；建议在内网或启用 BasicAuth 后开启。</div>
    </div>
  </div>
</template>
