<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { Download, Upload, FileJson, ShieldAlert, UploadCloud, Info, RefreshCw, Image as ImageIcon } from "lucide-vue-next";

import Badge from "../components/Badge.vue";
import Card from "../components/Card.vue";
import Button from "../components/Button.vue";
import PageHeader from "../components/PageHeader.vue";
import FormSelect from "../components/FormSelect.vue";
import Toggle from "../components/Toggle.vue";
import { api, type ConfigResponse } from "../api";
import { showToast } from "../toast";
import { type AccentColor, getAccentColor, setAccentColor, PALETTES } from "../theme";
import {
  browserNotificationsEnabled,
  browserNotificationsPermission,
  disableBrowserNotifications,
  enableBrowserNotifications,
} from "../browser_notifications";
import { resetRuntimeConfig, runtimeConfig } from "../runtime_config";
import { detectHost, isAutostartEnabled, requestAndRegisterPush, setAutostartEnabled } from "../capacitor_integration";
import { getLocale, setLocale, type Locale } from "../i18n";

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
const clearFlags = reactive({
  mp_password: false,
  mp_otp_password: false,
  cc_password: false,
});

function updateAccent(color: AccentColor) {
  accent.value = color;
  setAccentColor(color);
}

// Permission text surfaced next to the toggle so users understand why the
// toggle may be a no-op (browser denied / unsupported). Recomputed on each
// render since the browser may change the permission independently via
// site settings.
const notifPermissionLabel = computed(() => {
  const p = browserNotificationsPermission();
  if (p === "unsupported") return "当前浏览器不支持桌面通知";
  if (p === "denied") return "浏览器已拒绝授权，需在站点设置里重新允许";
  if (p === "default") return "尚未授权，开启时会请求浏览器权限";
  return "已授权";
});

// Remote-mode only: let users reset their saved apiBase + credentials so
// Onboarding re-runs on next launch. Browser + Tauri-embedded modes don't
// need this — browser users navigate to a different URL, Tauri-embedded
// always talks to the bundled sidecar.
const canResetConnection = computed(() => {
  const host = detectHost();
  return (host === "capacitor-ios" || host === "capacitor-android" || host === "tauri")
    && runtimeConfig.mode === "remote"
    && runtimeConfig.apiBase !== "";
});

const isCapacitorHost = computed(() => {
  const host = detectHost();
  return host === "capacitor-ios" || host === "capacitor-android";
});

const isTauriHost = computed(() => detectHost() === "tauri");

// Reactive autostart state — synced to native on mount, written-through when
// the toggle flips. Hidden entirely on non-Tauri hosts since autostart is a
// desktop-app concept.
const autostartEnabled = ref(false);
onMounted(async () => {
  if (isTauriHost.value) {
    autostartEnabled.value = await isAutostartEnabled();
  }
});

async function toggleAutostart(next: boolean) {
  const actual = await setAutostartEnabled(next);
  autostartEnabled.value = actual;
  if (actual === next) {
    showToast(next ? "已开启开机自启" : "已关闭开机自启", "success", 1800);
  } else {
    showToast("切换失败（权限不足或系统不支持）", "error", 2800);
  }
}

// Mobile push (APN/FCM). Stored token lives server-side; `pushRegistered`
// reflects the local registration attempt for this session only — we don't
// probe for "is the backend still subscribed" since re-tapping the button
// is idempotent on the server side.
const pushRegistered = ref(false);
const pushBusy = ref(false);

// Locale selector — reactive to the i18n singleton so the dropdown reflects
// the current state even if something else (e.g. browser nav) flipped it.
const currentLocale = ref<Locale>(getLocale());
const LOCALE_OPTIONS = [
  { label: "简体中文", value: "zh-CN" as Locale },
  { label: "English", value: "en-US" as Locale },
];
function onLocaleChange(next: Locale) {
  setLocale(next);
  currentLocale.value = next;
  showToast(next === "zh-CN" ? "已切换为中文" : "Language switched to English", "success", 1600);
}

async function enableMobilePush() {
  if (pushBusy.value) return;
  pushBusy.value = true;
  try {
    const token = await requestAndRegisterPush(async (t, platform) => {
      await api.deviceRegister(t, platform);
    });
    if (token) {
      pushRegistered.value = true;
      showToast("推送已注册（邀请开放时即时送达）", "success", 2600);
    } else {
      showToast("注册失败（检查系统通知权限）", "error", 3600);
    }
  } finally {
    pushBusy.value = false;
  }
}

async function resetConnection() {
  if (!(await confirm("确认重新连接服务器吗？本地保存的 URL / 凭证会被清除，下次启动会重新进入 Onboarding。"))) return;
  resetRuntimeConfig();
  showToast("已清除连接信息，即将重新加载…", "info", 1800);
  setTimeout(() => window.location.reload(), 1200);
}

async function toggleBrowserNotifications(next: boolean) {
  if (!next) {
    disableBrowserNotifications();
    showToast("已关闭桌面通知", "info", 1800);
    return;
  }
  const perm = await enableBrowserNotifications();
  if (perm === "granted") {
    showToast("桌面通知已开启：邀请开放时会推送", "success", 2600);
  } else if (perm === "unsupported") {
    showToast("当前浏览器不支持桌面通知", "error", 3000);
  } else {
    showToast("浏览器已拒绝授权，请在地址栏旁的权限设置里手动允许", "error", 4500);
  }
}

const model = reactive<Model>({
  moviepilot: { base_url: "", username: "", password: "", otp_password: "", sites_cache_ttl_seconds: 86400 },
  connectivity: { retry_interval_seconds: 3600, request_retry_delay_seconds: 30 },
  cookie: { source: "auto", cookiecloud: { base_url: "", uuid: "", password: "", refresh_interval_seconds: 300 } },
  scan: { interval_seconds: 600, timeout_seconds: 20, concurrency: 8, user_agent: "", trust_env: false },
  ui: { allow_state_reset: true },
});

watch(
  () => model.moviepilot.password,
  (v) => {
    if (String(v || "").trim()) clearFlags.mp_password = false;
  }
);
watch(
  () => model.moviepilot.otp_password,
  (v) => {
    if (String(v || "").trim()) clearFlags.mp_otp_password = false;
  }
);
watch(
  () => model.cookie.cookiecloud.password,
  (v) => {
    if (String(v || "").trim()) clearFlags.cc_password = false;
  }
);

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
  if (current !== baselineJson.value) return true;
  return !!(clearFlags.mp_password || clearFlags.mp_otp_password || clearFlags.cc_password);
});

async function load(opts: { toast?: boolean } = {}) {
  loading.value = true;
  try {
    const data = await api.configGet();
    view.value = data;
    clearFlags.mp_password = false;
    clearFlags.mp_otp_password = false;
    clearFlags.cc_password = false;
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
    const mpPassword = model.moviepilot.password.trim();
    const mpOtpPassword = model.moviepilot.otp_password.trim();
    const ccPassword = model.cookie.cookiecloud.password.trim();

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

    if (mpPassword) payload.moviepilot.password = mpPassword;
    else if (clearFlags.mp_password) payload.moviepilot.clear_password = true;

    if (mpOtpPassword) payload.moviepilot.otp_password = mpOtpPassword;
    else if (clearFlags.mp_otp_password) payload.moviepilot.clear_otp_password = true;

    if (ccPassword) payload.cookie.cookiecloud.password = ccPassword;
    else if (clearFlags.cc_password) payload.cookie.cookiecloud.clear_password = true;

    await api.configPut(payload);
    // Clear in-memory secret fields immediately so they don't linger after a successful save —
    // load() refreshes view state but doesn't reset the bound inputs unless the user re-enters them.
    model.moviepilot.password = "";
    model.moviepilot.otp_password = "";
    model.cookie.cookiecloud.password = "";
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
  let enabled = false;
  let minutes = 10;
  try {
    enabled = localStorage.getItem(STORAGE_REFRESH_ENABLED) === "1";
    const raw = Number(localStorage.getItem(STORAGE_REFRESH_MINUTES) || "10");
    if (Number.isFinite(raw)) minutes = raw;
  } catch {
    /* private mode / disabled — fall back to defaults */
  }
  return { enabled, minutes };
}

function _applyAutoRefreshPrefs(prefs: any) {
  const enabled = !!prefs?.enabled;
  const minutes = Number(prefs?.minutes ?? 10);
  try {
    localStorage.setItem(STORAGE_REFRESH_ENABLED, enabled ? "1" : "0");
    if (Number.isFinite(minutes) && minutes > 0) {
      localStorage.setItem(STORAGE_REFRESH_MINUTES, String(Math.round(minutes)));
    }
  } catch {
    /* ignore quota / disabled storage */
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
    let parsed: any;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error("文件不是合法的 JSON");
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("备份格式无效（应为 JSON 对象）");
    }
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

function beforeUnloadHandler(e: BeforeUnloadEvent) {
  if (!isDirty.value) return;
  e.preventDefault();
  e.returnValue = "";
}

onMounted(() => {
  load();
  window.addEventListener("beforeunload", beforeUnloadHandler);
});

onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", beforeUnloadHandler);
});

onBeforeRouteLeave(() => {
  if (!isDirty.value) return true;
  return window.confirm("有未保存的修改，确定离开吗？");
});

// Browser-local favicon cache controls. Clearing bumps a reactive version ref
// that every mounted <SiteIcon> watches, so icons refetch in place without a
// page reload. Useful after we ship a sourcing-logic fix (e.g. the redirect-
// guarded backend proxy) and want the new behavior to take effect immediately.
import {
  clearIconCache as _clearIconCache,
  getIconCacheSize as _getIconCacheSize,
} from "../icon_cache";

const iconCacheSize = ref(_getIconCacheSize());

async function clearIconCache() {
  if (!(await confirm("确认清除浏览器本地缓存的所有站点图标吗？\n清除后会立即触发当前页面的所有图标重新抓取。"))) return;
  try {
    _clearIconCache();
    iconCacheSize.value = 0;
    showToast("已清除图标缓存，正在重新抓取…", "success", 2400);
  } catch (e: any) {
    showToast(String(e?.message || e || "清除失败"), "error", 4500);
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader title="配置管理">
      <template #description>
        <div class="mt-2 flex items-center gap-3 text-base text-slate-500 dark:text-slate-300">
          <span>修改后需保存生效</span>
          <span v-if="isDirty" class="animate-pulse font-medium text-amber-600 dark:text-amber-400">
            ● 有未保存修改
          </span>
        </div>
      </template>
      <template #actions>
        <div class="flex items-center gap-2">
          <Button :disabled="loading" @click="reload">重载</Button>
          <Button variant="primary" :disabled="saving || !isDirty" :loading="saving" @click="save">保存</Button>
          <Button variant="danger" title="重置 webui 配置" @click="resetAll">重置</Button>
        </div>
      </template>
    </PageHeader>

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
              :disabled="backupBusy" @click="exportBackup(false)">
              <FileJson
                class="h-6 w-6 text-slate-400 transition-colors group-hover:text-brand-500 dark:text-slate-400" />
              <div class="text-center">
                <div class="text-sm font-medium text-slate-700 dark:text-slate-200">仅配置 (脱敏)</div>
                <div class="text-[10px] text-slate-400 dark:text-slate-400">不含密钥/密码</div>
              </div>
            </button>
            <button
              class="group relative flex flex-col items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50/50 p-4 transition-all hover:-translate-y-0.5 hover:border-rose-200 hover:bg-rose-50/30 hover:shadow-md active:translate-y-0 dark:border-slate-800 dark:bg-slate-900/50 dark:hover:border-rose-700/50 dark:hover:bg-rose-900/20"
              :disabled="backupBusy" @click="exportBackup(true)">
              <ShieldAlert
                class="h-6 w-6 text-slate-400 transition-colors group-hover:text-rose-500 dark:text-slate-400" />
              <div class="text-center">
                <div class="text-sm font-medium text-slate-700 dark:text-slate-200">完整导出</div>
                <div class="text-[10px] text-slate-400 dark:text-slate-400">含敏感密钥信息</div>
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
            :class="{ 'border-brand-500 bg-brand-50/10': importFile }">
            <input type="file" accept="application/json" class="absolute inset-0 cursor-pointer opacity-0"
              @change="onPickFile" />
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
            <Button class="flex-1" :disabled="backupBusy || !importFile" :loading="backupBusy" @click="importBackup"
              variant="primary">
              导入恢复
            </Button>
          </div>
        </div>
      </div>

      <div
        class="mt-6 flex items-start gap-2 rounded-lg bg-slate-100/50 p-3 text-xs text-slate-500 dark:bg-slate-900/30 dark:text-slate-300">
        <Info class="h-4 w-4 shrink-0 mt-0.5 text-slate-400" />
        备份文件额外包含浏览器本地的“自动刷新”偏好；导入后将写入当前浏览器配置。
      </div>

      <div v-if="importScanPrompt"
        class="mt-4 rounded-xl border border-brand-200 bg-brand-50/80 p-4 backdrop-blur-sm dark:border-brand-900/50 dark:bg-brand-950/30">
        <div class="flex items-center justify-between gap-4">
          <div class="flex items-center gap-3">
            <div
              class="flex h-10 w-10 items-center justify-center rounded-full bg-brand-100 text-brand-600 dark:bg-brand-900/50 dark:text-brand-400">
              <RefreshCw class="h-5 w-5" :class="{ 'animate-spin': scanNowRunning }" />
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
          <Badge v-if="view" :label="view.moviepilot.password_configured ? 'password 已配置' : 'password 未配置'"
            :tone="view.moviepilot.password_configured ? 'green' : 'amber'" />
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
            <input v-model="model.moviepilot.password" type="password" class="mt-1 ui-input"
              :placeholder="view?.moviepilot.password_configured ? '已配置' : '未配置'" />
            <div class="mt-2 flex items-center justify-between gap-3">
              <div v-if="clearFlags.mp_password" class="text-xs font-medium text-amber-600 dark:text-amber-400">
                将清除已保存 password（回退到 config.yaml/env）
              </div>
              <div v-else class="text-xs text-slate-500 dark:text-slate-300"></div>
              <Button v-if="view?.moviepilot.password_configured" variant="ghost" size="sm" @click="clearFlags.mp_password = !clearFlags.mp_password">
                {{ clearFlags.mp_password ? "取消清除" : "清除已保存密码" }}
              </Button>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium">OTP 密码（可选，留空不修改）</label>
            <input v-model="model.moviepilot.otp_password" type="password" class="mt-1 ui-input"
              :placeholder="view?.moviepilot.otp_configured ? '已配置' : '未配置'" />
            <div class="mt-2 flex items-center justify-between gap-3">
              <div v-if="clearFlags.mp_otp_password" class="text-xs font-medium text-amber-600 dark:text-amber-400">
                将清除已保存 OTP（回退到 config.yaml/env）
              </div>
              <div v-else class="text-xs text-slate-500 dark:text-slate-300"></div>
              <Button v-if="view?.moviepilot.otp_configured" variant="ghost" size="sm" @click="clearFlags.mp_otp_password = !clearFlags.mp_otp_password">
                {{ clearFlags.mp_otp_password ? "取消清除" : "清除已保存 OTP" }}
              </Button>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium">站点列表缓存 TTL（秒）</label>
            <input v-model.number="model.moviepilot.sites_cache_ttl_seconds" type="number" min="60" max="604800"
              class="mt-1 ui-input" />
            <div class="mt-1 text-xs text-slate-500 dark:text-slate-300">MoviePilot 拉取失败时，未过期缓存可用于继续扫描。</div>
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
                <input v-model="model.cookie.cookiecloud.base_url" class="mt-1 ui-input"
                  placeholder="http://cookiecloud:8088" />
              </div>
              <div>
                <label class="block text-sm font-medium">UUID</label>
                <input v-model="model.cookie.cookiecloud.uuid" class="mt-1 ui-input" placeholder="xxxx" />
              </div>
              <div>
                <label class="block text-sm font-medium">密码（留空不修改）</label>
                <input v-model="model.cookie.cookiecloud.password" type="password" class="mt-1 ui-input"
                  :placeholder="view?.cookie.cookiecloud.password_configured ? '已配置' : '未配置'" />
                <div class="mt-2 flex items-center justify-between gap-3">
                  <div v-if="clearFlags.cc_password" class="text-xs font-medium text-amber-600 dark:text-amber-400">
                    将清除已保存密码（回退到 config.yaml/env）
                  </div>
                  <div v-else class="text-xs text-slate-500 dark:text-slate-300"></div>
                  <Button v-if="view?.cookie.cookiecloud.password_configured" variant="ghost" size="sm"
                    @click="clearFlags.cc_password = !clearFlags.cc_password">
                    {{ clearFlags.cc_password ? "取消清除" : "清除已保存密码" }}
                  </Button>
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium">刷新间隔（秒）</label>
                <input v-model.number="model.cookie.cookiecloud.refresh_interval_seconds" type="number" min="30"
                  max="86400" class="mt-1 ui-input" />
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
          <input v-model.number="model.scan.interval_seconds" type="number" min="30" max="86400"
            class="mt-1 ui-input" />
        </div>
        <div>
          <FormSelect v-model="model.connectivity.retry_interval_seconds" label="依赖重试间隔（MoviePilot / CookieCloud）"
            :options="RETRY_INTERVAL_OPTIONS">
            <template #help>
              <div class="mt-1 text-xs text-slate-600 dark:text-slate-300">依赖连接失败时会优先使用缓存，并按此间隔重新尝试恢复连接。</div>
            </template>
          </FormSelect>
        </div>
        <div>
          <FormSelect v-model="model.connectivity.request_retry_delay_seconds" label="网络请求失败重试延迟（站点探测 / 通知）"
            :options="REQUEST_RETRY_DELAY_OPTIONS">
            <template #help>
              <div class="mt-1 text-xs text-slate-600 dark:text-slate-300">遇到网络异常/5xx/429/408 时会按此间隔重试（最多 3 次）。</div>
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
        <!-- Language selector — always available. Browser users, Tauri users,
             Capacitor users all see it the same way. Takes effect immediately
             without reload since vue-i18n's reactive locale ref is bound into
             every $t() call across the app. -->
        <div>
          <label class="block text-sm font-medium">{{ $t("config.language") }}</label>
          <div class="mt-2 w-56">
            <FormSelect
              :model-value="currentLocale"
              :options="LOCALE_OPTIONS"
              @update:modelValue="(v) => onLocaleChange(v as any)"
            />
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium">主题强调色 (Accent Color)</label>
          <div class="mt-2 flex flex-wrap gap-2">
            <button v-for="color in ['indigo', 'emerald', 'rose', 'amber', 'violet']" :key="color"
              class="group relative flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 transition-colors dark:border-slate-700"
              :class="{ 'ring-2 ring-slate-400 dark:ring-slate-500': accent === color }"
              :style="{ backgroundColor: `rgb(${PALETTES[color as AccentColor][500]})` }"
              @click="updateAccent(color as any)" :title="color">
              <!-- We use the semantic classes for preview buttons to avoid circular dependency on brand var for non-active ones?
                   Actually we defined brand vars. But for 'emerald' button we want it green even if brand is indigo.
                   So we need hardcoded preview colors or style override.
                   Wait, I didn't define --color-emerald-500 globally. I only set --color-brand-* to the chosen palette.
                   So I need hardcoded colors for the picker buttons.
              -->
              <span v-if="accent === color" class="h-2.5 w-2.5 rounded-full bg-white shadow-sm" />
            </button>
          </div>
          <div class="mt-1 text-xs text-slate-500 dark:text-slate-300">选择您喜欢的品牌色调，即时生效。</div>
        </div>

        <div class="flex items-center gap-3">
          <Toggle v-model="model.ui.allow_state_reset" />
          <div class="text-sm text-slate-700 dark:text-slate-200">允许在“站点状态”页显示“重置状态”按钮</div>
        </div>
        <div class="mt-1 text-xs text-slate-500 dark:text-slate-300">用于清空扫描结果（不影响站点配置）；建议在内网或启用 BasicAuth 后开启。</div>

        <!-- Desktop-only: launch at login. Shown only on Tauri shells because
             browser / Capacitor mobile have no equivalent concept. Paired
             with the T4 tray so the app can live in the background from
             boot without requiring a window. -->
        <div v-if="isTauriHost" class="mt-4 flex items-start gap-3">
          <Toggle :modelValue="autostartEnabled" @update:modelValue="toggleAutostart" />
          <div>
            <div class="text-sm text-slate-700 dark:text-slate-200">开机自启</div>
            <div class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              系统启动后自动在后台运行（macOS LaunchAgent / Windows 启动注册表 / Linux .desktop 自启项）。
              关闭窗口即隐藏到托盘，退出请用托盘菜单。
            </div>
          </div>
        </div>

        <!-- Capacitor mobile: native push via APN/FCM. Shown instead of the
             browser Notification toggle (which doesn't work in the WebView).
             Requires operator to set PTIW_FCM_SERVER_KEY / APNS_* env vars
             server-side; without them the backend stores the token but
             never dispatches. -->
        <div v-if="isCapacitorHost" class="mt-4 flex items-start gap-3">
          <Button size="sm" variant="primary" :disabled="pushBusy || pushRegistered" :loading="pushBusy" @click="enableMobilePush">
            {{ pushRegistered ? "已开启" : "开启" }}
          </Button>
          <div>
            <div class="text-sm text-slate-700 dark:text-slate-200">原生推送通知</div>
            <div class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              邀请开放时通过 APN（iOS）/ FCM（Android）即时推送，锁屏也能收到。
              服务端需配置 PTIW_FCM_SERVER_KEY / PTIW_APNS_* 环境变量。
            </div>
          </div>
        </div>

        <!-- Browser Notification API is a no-op inside the Capacitor WebView
             (mobile native notifications go through the native-push path
             above, not `window.Notification`). Hide this toggle there. -->
        <div v-if="!isCapacitorHost" class="mt-4 flex items-start gap-3">
          <Toggle
            :modelValue="browserNotificationsEnabled"
            @update:modelValue="toggleBrowserNotifications"
          />
          <div>
            <div class="text-sm text-slate-700 dark:text-slate-200">桌面通知（浏览器后台标签页也能收到邀请开放提醒）</div>
            <div class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {{ notifPermissionLabel }} ·
              服务端 Telegram / 企业微信通知保持独立，两者互不冲突。
            </div>
          </div>
        </div>

        <div class="mt-4 rounded-xl border border-slate-200 bg-slate-50/50 p-4 dark:border-slate-800 dark:bg-slate-900/40">
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-start gap-3">
              <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
                <ImageIcon class="h-4 w-4" />
              </div>
              <div>
                <div class="text-sm font-medium text-slate-800 dark:text-slate-100">站点图标缓存</div>
                <div class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  当前浏览器缓存：<span class="tabular-nums">{{ iconCacheSize }}</span> 个站点（30 天 TTL，过期条目下次渲染时自动清理）。
                  点击“清除缓存”会立即让当前页面所有图标重新抓取——无需刷新页面。
                </div>
              </div>
            </div>
            <div class="flex shrink-0 gap-2">
              <Button size="sm" :disabled="iconCacheSize === 0" @click="clearIconCache">清除缓存</Button>
            </div>
          </div>
        </div>

        <!-- Reset server connection. Only shown in the Capacitor / Tauri shells
             when already configured for remote mode — browser users change
             server by navigating to a different URL, not via this control. -->
        <div v-if="canResetConnection" class="mt-4 rounded-xl border border-danger-200/70 bg-danger-50/30 p-4 dark:border-danger-900/50 dark:bg-danger-950/20">
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-start gap-3">
              <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-danger-100 text-danger-600 dark:bg-danger-500/15 dark:text-danger-300">
                <ShieldAlert class="h-4 w-4" />
              </div>
              <div>
                <div class="text-sm font-medium text-slate-800 dark:text-slate-100">重新连接服务器</div>
                <div class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  当前连接：<span class="font-mono">{{ runtimeConfig.apiBase }}</span>。
                  需要切换到其他 FastAPI 实例？清除后下次启动会重新进入 Onboarding 流程。
                </div>
              </div>
            </div>
            <div class="flex shrink-0 gap-2">
              <Button size="sm" variant="danger" @click="resetConnection">清除连接</Button>
            </div>
          </div>
        </div>
      </div>
    </Card>
  </div>
</template>
