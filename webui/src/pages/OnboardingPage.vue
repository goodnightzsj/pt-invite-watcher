<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowRight, Loader2, Server, Laptop } from "lucide-vue-next";

import Button from "../components/Button.vue";
import FormInput from "../components/FormInput.vue";
import { HttpError } from "../api";
import { saveRemoteConfig } from "../runtime_config";

/**
 * First-run flow shown inside the Tauri shell when no API base is configured.
 *
 * There are two terminal states:
 *
 * - **Remote** (always supported, default on mobile): user types a FastAPI
 *   URL + BasicAuth, we validate by GETting `/api/version`, persist, and let
 *   the shell reload into the normal dashboard.
 * - **Embedded** (desktop only, shown only when the Tauri shell tells us a
 *   sidecar is bundled): the shell has already populated runtime config via
 *   `window.__PTIW_RUNTIME__`, so this component isn't rendered in that case.
 *
 * Pure browser deployments (served directly by FastAPI) never see this page —
 * apiBase defaults to empty string → same-origin → Onboarding is not required.
 */

type Step = "pick" | "remote";

const step = ref<Step>("pick");
const apiBase = ref("");
const username = ref("");
const password = ref("");
const submitting = ref(false);
const errorMsg = ref("");

const canSubmit = computed(() => apiBase.value.trim().length > 0 && !submitting.value);

function base64UserPass(user: string, pass: string): string {
    // btoa requires Latin-1; typical BasicAuth credentials fit, but guard with
    // a UTF-8→base64 dance so non-ASCII usernames don't silently break.
    const raw = `${user}:${pass}`;
    try {
        return btoa(unescape(encodeURIComponent(raw)));
    } catch {
        return btoa(raw);
    }
}

async function connect() {
    if (!canSubmit.value) return;
    submitting.value = true;
    errorMsg.value = "";
    try {
        const base = apiBase.value.trim().replace(/\/$/, "");
        if (!/^https?:\/\//i.test(base)) {
            throw new Error("URL 必须以 http:// 或 https:// 开头");
        }
        const auth = (username.value || password.value) ? base64UserPass(username.value, password.value) : "";
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (auth) headers.Authorization = `Basic ${auth}`;
        // Sanity-probe the endpoint so we don't save bogus settings that would
        // leave the dashboard stuck on 401/404 after a reload.
        const resp = await fetch(`${base}/api/version`, { headers });
        if (resp.status === 401) throw new Error("用户名或密码不正确（BasicAuth 401）");
        if (!resp.ok) throw new Error(`服务器响应异常：HTTP ${resp.status}`);
        saveRemoteConfig(base, auth);
        // Reload so every part of the app re-reads the new runtime config and
        // the WebSocket reconnects to the right origin.
        window.location.reload();
    } catch (e: any) {
        if (e instanceof HttpError) {
            errorMsg.value = `连接失败：${e.status} ${e.statusText}`;
        } else if (e instanceof TypeError) {
            // CORS / DNS / unreachable all surface here as "Failed to fetch".
            errorMsg.value = "无法连接到该地址（检查 URL 是否可达 / CORS 是否允许当前 origin）";
        } else {
            errorMsg.value = String(e?.message || e);
        }
    } finally {
        submitting.value = false;
    }
}
</script>

<template>
    <div class="mx-auto flex min-h-screen w-full max-w-xl flex-col items-center justify-center px-5 py-10">
        <div class="w-full space-y-6 rounded-2xl border border-white/20 bg-white/60 p-8 shadow-xl backdrop-blur-md dark:border-white/10 dark:bg-slate-900/60">
            <div class="space-y-1 text-center">
                <div class="text-2xl font-bold text-slate-900 dark:text-slate-100">欢迎使用 PT Invite Watcher</div>
                <div class="text-sm text-slate-500 dark:text-slate-300">首次启动，请选择数据来源</div>
            </div>

            <div v-if="step === 'pick'" class="space-y-3">
                <button
                    type="button"
                    class="flex w-full items-start gap-4 rounded-xl border border-slate-200 bg-white/70 p-4 text-left transition-all hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md dark:border-slate-700 dark:bg-slate-900/60"
                    @click="step = 'remote'"
                >
                    <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
                        <Server class="h-5 w-5" />
                    </div>
                    <div class="min-w-0 flex-1">
                        <div class="font-semibold text-slate-900 dark:text-slate-100">连接到已有服务器（云端模式）</div>
                        <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                            已在服务器上运行了一个 FastAPI 实例？填入 URL 和 BasicAuth 即可。适合多端同步 / 24 小时常驻扫描。
                        </div>
                    </div>
                    <ArrowRight class="mt-2 h-4 w-4 shrink-0 text-slate-400" />
                </button>

                <div class="rounded-xl border border-dashed border-slate-200 bg-slate-50/40 p-4 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-400">
                    <div class="flex items-start gap-3">
                        <Laptop class="h-4 w-4 shrink-0 text-slate-400" />
                        <div>
                            <div class="font-medium text-slate-600 dark:text-slate-300">本地模式（打包桌面版自动启用）</div>
                            <div class="mt-1">
                                桌面安装包内置 Python 核心，会在本机空闲端口启动并写入本地 SQLite。
                                这种模式下你不会看到这个页面 — 直接进入 Dashboard。
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <form v-else-if="step === 'remote'" class="space-y-4" @submit.prevent="connect">
                <FormInput
                    v-model="apiBase"
                    label="服务器 URL"
                    placeholder="https://pt.example.com 或 http://192.168.1.10:8080"
                />
                <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <FormInput v-model="username" label="用户名" placeholder="BasicAuth 用户名（可选）" />
                    <FormInput v-model="password" type="password" label="密码" placeholder="BasicAuth 密码（可选）" />
                </div>
                <div v-if="errorMsg" class="rounded-lg border border-danger-200 bg-danger-50 px-3 py-2 text-sm text-danger-700 dark:border-danger-900 dark:bg-danger-950/40 dark:text-danger-200">
                    {{ errorMsg }}
                </div>
                <div class="flex items-center justify-between gap-2">
                    <Button type="button" @click="step = 'pick'">返回</Button>
                    <Button type="submit" variant="primary" :disabled="!canSubmit" :loading="submitting">
                        <Loader2 v-if="submitting" class="mr-1 h-4 w-4 animate-spin" />
                        连接并进入
                    </Button>
                </div>
            </form>
        </div>
    </div>
</template>
