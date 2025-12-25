<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import Badge from "../components/Badge.vue";
import Toggle from "../components/Toggle.vue";
import { api, type ConfigResponse } from "../api";
import { showToast } from "../toast";

type Model = {
  moviepilot: { base_url: string; username: string; password: string; otp_password: string };
  cookie: { source: string; cookiecloud: { base_url: string; uuid: string; password: string; refresh_interval_seconds: number } };
  scan: { interval_seconds: number; timeout_seconds: number; concurrency: number; user_agent: string; trust_env: boolean };
};

const loading = ref(false);
const saving = ref(false);
const view = ref<ConfigResponse | null>(null);
const model = reactive<Model>({
  moviepilot: { base_url: "", username: "", password: "", otp_password: "" },
  cookie: { source: "auto", cookiecloud: { base_url: "", uuid: "", password: "", refresh_interval_seconds: 300 } },
  scan: { interval_seconds: 600, timeout_seconds: 20, concurrency: 8, user_agent: "", trust_env: false },
});

async function load() {
  loading.value = true;
  try {
    const data = await api.configGet();
    view.value = data;
    model.moviepilot.base_url = data.moviepilot.base_url || "";
    model.moviepilot.username = data.moviepilot.username || "";
    model.moviepilot.password = "";
    model.moviepilot.otp_password = "";

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
  } catch (e: any) {
    showToast(String(e?.message || e || "加载失败"), "error");
  } finally {
    loading.value = false;
  }
}

async function save() {
  saving.value = true;
  try {
    const payload: any = {
      moviepilot: {
        base_url: model.moviepilot.base_url,
        username: model.moviepilot.username,
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
    await api.configReset();
    showToast("已重置", "success");
    await load();
  } catch (e: any) {
    showToast(String(e?.message || e || "重置失败"), "error");
  }
}

onMounted(() => load());
</script>

<template>
  <div class="space-y-5">
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
            @click="load"
          >
            {{ loading ? "加载中…" : "重新加载" }}
          </button>
          <button
            class="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
            :disabled="saving"
            @click="save"
          >
            {{ saving ? "保存中…" : "保存" }}
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
            <label class="block text-sm font-medium">Username</label>
            <input v-model="model.moviepilot.username" class="mt-1 ui-input" placeholder="admin" />
          </div>
          <div>
            <label class="block text-sm font-medium">Password（留空不修改）</label>
            <input
              v-model="model.moviepilot.password"
              type="password"
              class="mt-1 ui-input"
              :placeholder="view?.moviepilot.password_configured ? '已配置' : '未配置'"
            />
          </div>
          <div>
            <label class="block text-sm font-medium">OTP Password（可选，留空不修改）</label>
            <input
              v-model="model.moviepilot.otp_password"
              type="password"
              class="mt-1 ui-input"
              :placeholder="view?.moviepilot.otp_configured ? '已配置' : '未配置'"
            />
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
            <label class="block text-sm font-medium">Cookie Source</label>
            <select v-model="model.cookie.source" class="mt-1 ui-select">
              <option value="auto">auto（优先 CookieCloud，失败回退 MoviePilot）</option>
              <option value="cookiecloud">cookiecloud</option>
              <option value="moviepilot">moviepilot</option>
            </select>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
            <div class="mb-3 text-sm font-semibold">CookieCloud（可选）</div>
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
                <label class="block text-sm font-medium">Password（留空不修改）</label>
                <input
                  v-model="model.cookie.cookiecloud.password"
                  type="password"
                  class="mt-1 ui-input"
                  :placeholder="view?.cookie.cookiecloud.password_configured ? '已配置' : '未配置'"
                />
              </div>
              <div>
                <label class="block text-sm font-medium">Refresh Interval Seconds</label>
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
        <div class="text-sm font-semibold">Scan</div>
        <Badge :label="`interval=${model.scan.interval_seconds}s`" tone="slate" />
      </div>

      <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label class="block text-sm font-medium">Interval Seconds（保存后下一轮生效）</label>
          <input v-model.number="model.scan.interval_seconds" type="number" min="30" max="86400" class="mt-1 ui-input" />
        </div>
        <div>
          <label class="block text-sm font-medium">Timeout Seconds</label>
          <input v-model.number="model.scan.timeout_seconds" type="number" min="5" max="180" class="mt-1 ui-input" />
        </div>
        <div>
          <label class="block text-sm font-medium">Concurrency</label>
          <input v-model.number="model.scan.concurrency" type="number" min="1" max="64" class="mt-1 ui-input" />
        </div>
        <div>
          <label class="block text-sm font-medium">User-Agent（留空表示使用默认/站点自带 UA）</label>
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
  </div>
</template>
