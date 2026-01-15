<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Download, Upload, FileJson, ShieldAlert, UploadCloud, Info, RefreshCw } from "lucide-vue-next";

import Badge from "../components/Badge.vue";
import Card from "../components/Card.vue";
import Button from "../components/Button.vue";
import FormSelect from "../components/FormSelect.vue";
import Toggle from "../components/Toggle.vue";
import { api, type ConfigResponse } from "../api";
import { showToast } from "../toast";
import { type AccentColor, getAccentColor, setAccentColor, PALETTES } from "../theme";

const STORAGE_REFRESH_ENABLED = "ptiw_auto_refresh_enabled";
const STORAGE_REFRESH_MINUTES = "ptiw_auto_refresh_minutes";

const IMPORT_MODE_OPTIONS = [
  { label: "merge", value: "merge", help: "合并，保留本地敏感字段" },
  { label: "replace", value: "replace", help: "覆盖，按备份为准" },
];

const COOKIE_SOURCE_OPTIONS = [
  { label: "auto", value: "auto", help: "CookieCloud 优先，失败回退 MoviePilot" },
  { label: "cookiecloud", value: "cookiecloud", help: "仅 CookieCloud" },
  { label: "moviepilot", value: "moviepilot", help: "仅 MoviePilot" },
];

const RETRY_INTERVAL_OPTIONS = [
  { label: "1 分钟", value: 60 },
  { label: "5 分钟", value: 300 },
  { label: "10 分钟", value: 600 },
  { label: "30 分钟", value: 1800 },
  { label: "60 分钟", value: 3600 },
  { label: "2 小时", value: 7200 },
  { label: "6 小时", value: 21600 },
  { label: "12 小时", value: 43200 },
  { label: "24 小时", value: 86400 },
];

const REQUEST_RETRY_DELAY_OPTIONS = [
  { label: "30 秒", value: 30 },
  { label: "60 秒", value: 60 },
  { label: "5 分钟", value: 300 },
  { label: "10 分钟", value: 600 },
  { label: "30 分钟", value: 1800 },
  { label: "60 分钟", value: 3600 },
  { label: "2 小时", value: 7200 },
  { label: "6 小时", value: 21600 },
  { label: "12 小时", value: 43200 },
  { label: "24 小时", value: 86400 },
];

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
const accent = ref<AccentColor>(getAccentColor());

function updateAccent(color: AccentColor) {
  accent.value = color;
  setAccentColor(color);
}

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

import { confirm } from "../confirm";

async function resetAll() {
  if (!(await confirm("确认清空 Web UI 配置并回退到 config.yaml/env 吗？"))) return;
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
  <div class="space-y-6">
    <!-- Header Actions -->
    <Card padding="sm" :hoverable="false" class="sticky top-[4rem] z-20 max-sm:top-[7rem]">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 class="text-base font-bold text-slate-900 dark:text-white">配置管理</h2>
          <div class="mt-0.5 flex gap-2 text-xs">
            <span v-if="isDirty" class="text-amber-600 dark:text-amber-400">● 有未保存修改</span>
            <span class="text-slate-600 dark:text-slate-400">修改后需保存生效</span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <Button :disabled="loading" @click="reload">重载</Button>
          <Button variant="primary" :disabled="saving || !isDirty" @click="save">保存</Button>
          <Button variant="danger" title="重置 webui 配置" @click="resetAll">重置</Button>
        </div>
      </div>
    </Card>

    <Card title="配置备份与恢复">
      <template #description>
        备份本服务 SQLite 中的运行时配置（服务配置/通知设置/站点管理）；不包含扫描结果与历史。
      </template>

      <div class="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <!-- Export Section -->
        <div class="space-y-4">
          <div class="text-sm font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
            <Download class="w-4 h-4 text-brand-500" />
            <span>导出配置</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              class="group relative flex flex-col items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50/50 p-4 transition-all hover:-translate-y-0.5 hover:border-brand-200 hover:bg-brand-50/30 hover:shadow-md active:translate-y-0 dark:border-slate-800 dark:bg-slate-900/50 dark:hover:border-brand-700/50 dark:hover:bg-brand-900/20"
              :disabled="backupBusy"
              @click="exportBackup(false)"
            >
              <FileJson class="h-6 w-6 text-slate-400 transition-colors group-hover:text-brand-500 dark:text-slate-500" />
              <div class="text-center">
                <div class="text-sm font-medium text-slate-700 dark:text-slate-200">仅配置 (脱敏)</div>
                <div class="text-[10px] text-slate-400 dark:text-slate-500">不含密钥/密码</div>
              </div>
            </button>
            <button
              class="group relative flex flex-col items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50/50 p-4 transition-all hover:-translate-y-0.5 hover:border-rose-200 hover:bg-rose-50/30 hover:shadow-md active:translate-y-0 dark:border-slate-800 dark:bg-slate-900/50 dark:hover:border-rose-700/50 dark:hover:bg-rose-900/20"
              :disabled="backupBusy"
              @click="exportBackup(true)"
            >
              <ShieldAlert class="h-6 w-6 text-slate-400 transition-colors group-hover:text-rose-500 dark:text-slate-500" />
              <div class="text-center">
                <div class="text-sm font-medium text-slate-700 dark:text-slate-200">完整导出</div>
                <div class="text-[10px] text-slate-400 dark:text-slate-500">含敏感密钥信息</div>
              </div>
            </button>
          </div>
        </div>

        <!-- Import Section -->
        <div class="space-y-4">
          <div class="text-sm font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
            <Upload class="w-4 h-4 text-brand-500" />
            <span>恢复配置</span>
          </div>
          
          <div 
            class="relative rounded-xl border-2 border-dashed border-slate-200 bg-slate-50/30 p-4 transition-all hover:border-brand-300 hover:bg-brand-50/20 dark:border-slate-800 dark:bg-slate-900/30 dark:hover:border-brand-700/50 dark:hover:bg-brand-900/10"
            :class="{'border-brand-500 bg-brand-50/10': importFile}"
          >
            <input
              type="file"
              accept="application/json"
              class="absolute inset-0 cursor-pointer opacity-0"
              @change="onPickFile"
            />
            <div class="flex flex-col items-center justify-center gap-2 py-2">
              <div v-if="!importFile" class="flex flex-col items-center gap-1 text-slate-400">
                <UploadCloud class="h-8 w-8 mb-1 opacity-50" />
                <span class="text-xs">点击或拖拽 JSON 文件至此</span>
              </div>
              <div v-else class="flex flex-col items-center gap-1 text-brand-600 dark:text-brand-400">
                <FileJson class="h-8 w-8 mb-1" />
                <span class="text-xs font-medium">{{ importFile.name }}</span>
                <span class="text-[10px] opacity-70">点击更换文件</span>
              </div>
            </div>
          </div>

          <div class="flex gap-2">
             <div class="w-32">
                <FormSelect v-model="importMode" :options="IMPORT_MODE_OPTIONS" :disabled="backupBusy" dense />
             </div>
             <Button class="flex-1" :disabled="backupBusy || !importFile" :loading="backupBusy" @click="importBackup" variant="primary">
               导入恢复
             </Button>
          </div>
        </div>
      </div>

      <div class="mt-6 flex items-start gap-2 rounded-lg bg-slate-100/50 p-3 text-xs text-slate-500 dark:bg-slate-900/30 dark:text-slate-400">
        <Info class="h-4 w-4 shrink-0 mt-0.5 text-slate-400" />
        备份文件额外包含浏览器本地的“自动刷新”偏好；导入后将写入当前浏览器配置。
      </div>

      <div
        v-if="importScanPrompt"
        class="mt-4 rounded-xl border border-brand-200 bg-brand-50/80 p-4 backdrop-blur-sm dark:border-brand-900/50 dark:bg-brand-950/30"
      >
        <div class="flex items-center justify-between gap-4">
          <div class="flex items-center gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-full bg-brand-100 text-brand-600 dark:bg-brand-900/50 dark:text-brand-400">
              <RefreshCw class="h-5 w-5" :class="{'animate-spin': scanNowRunning}" />
            </div>
            <div>
              <div class="text-sm font-semibold text-brand-900 dark:text-brand-100">配置已恢复</div>
              <div class="text-xs text-brand-700/80 dark:text-brand-300/60">
                建议立即进行一次状态扫描以同步站点数据。
              </div>
            </div>
          </div>
          <Button variant="primary" size="sm" :disabled="scanNowRunning" :loading="scanNowRunning" @click="runScanNow">
            立即扫描
          </Button>
        </div>
      </div>
    </Card>

    <div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <Card>
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
      </Card>

      <Card>
        <div class="mb-4 flex items-center justify-between">
          <div class="text-sm font-semibold">Cookie</div>
          <Badge :label="model.cookie.source" tone="slate" />
        </div>

        <div class="space-y-4">
          <FormSelect v-model="model.cookie.source" label="Cookie 来源" :options="COOKIE_SOURCE_OPTIONS" />
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
      </Card>
    </div>

    <Card>
      <div class="mb-4 flex items-center justify-between">
        <div class="text-sm font-semibold">扫描策略</div>
        <Badge :label="`interval=${model.scan.interval_seconds}s`" tone="slate" />
      </div>

      <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label class="block text-sm font-medium">间隔（秒，保存后下一轮生效）</label>
          <input v-model.number="model.scan.interval_seconds" type="number" min="30" max="86400" class="mt-1 ui-input" />
        </div>
        <div>
          <FormSelect v-model="model.connectivity.retry_interval_seconds" label="依赖重试间隔（MoviePilot / CookieCloud）" :options="RETRY_INTERVAL_OPTIONS">
            <template #help>
              <div class="mt-1 text-xs text-slate-600 dark:text-slate-400">依赖连接失败时会优先使用缓存，并按此间隔重新尝试恢复连接。</div>
            </template>
          </FormSelect>
        </div>
        <div>
          <FormSelect v-model="model.connectivity.request_retry_delay_seconds" label="网络请求失败重试延迟（站点探测 / 通知）" :options="REQUEST_RETRY_DELAY_OPTIONS">
            <template #help>
              <div class="mt-1 text-xs text-slate-600 dark:text-slate-400">遇到网络异常/5xx/429/408 时会按此间隔重试（最多 3 次）。</div>
            </template>
          </FormSelect>
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
    </Card>

    <Card title="界面设置">
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium">主题强调色 (Accent Color)</label>
          <div class="mt-2 flex flex-wrap gap-2">
            <button
              v-for="color in ['indigo', 'emerald', 'rose', 'amber', 'violet']"
              :key="color"
              class="group relative flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 transition-colors dark:border-slate-700"
              :class="{ 'ring-2 ring-slate-400 dark:ring-slate-500': accent === color }"
              :style="{ backgroundColor: `rgb(${PALETTES[color as AccentColor][500]})` }" 
              @click="updateAccent(color as any)"
              :title="color"
            >
              <!-- We use the semantic classes for preview buttons to avoid circular dependency on brand var for non-active ones?
                   Actually we defined brand vars. But for 'emerald' button we want it green even if brand is indigo.
                   So we need hardcoded preview colors or style override.
                   Wait, I didn't define --color-emerald-500 globally. I only set --color-brand-* to the chosen palette.
                   So I need hardcoded colors for the picker buttons.
              -->
              <span v-if="accent === color" class="h-2.5 w-2.5 rounded-full bg-white shadow-sm" />
            </button>
          </div>
          <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">选择您喜欢的品牌色调，即时生效。</div>
        </div>
        
        <div class="flex items-center gap-3">
          <Toggle v-model="model.ui.allow_state_reset" />
          <div class="text-sm text-slate-700 dark:text-slate-200">允许在“站点状态”页显示“重置状态”按钮</div>
        </div>
        <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">用于清空扫描结果（不影响站点配置）；建议在内网或启用 BasicAuth 后开启。</div>
      </div>
    </Card>
  </div>
</template>
