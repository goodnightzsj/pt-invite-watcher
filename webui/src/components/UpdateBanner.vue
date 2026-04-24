<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Download, RefreshCw } from "lucide-vue-next";

import Button from "./Button.vue";
import { detectHost } from "../capacitor_integration";
import { showToast } from "../toast";

/**
 * Self-update banner for Tauri desktop. Hidden on browser + Capacitor where
 * update is either N/A (browser reloads to latest anyway) or handled by the
 * OS store (Play Store / App Store).
 *
 * Flow:
 *   1. On mount, Tauri shell → `plugin:updater|check` → returns update info
 *      or null. ~2s silent probe, doesn't block other UI.
 *   2. If available, render a small top banner with the new version +
 *      "立即更新" / "稍后" buttons.
 *   3. User clicks 立即更新: `plugin:updater|downloadAndInstall` downloads
 *      + verifies the .sig against the baked-in pubkey, then calls
 *      `plugin:process|restart` to relaunch.
 *
 * All failures swallow silently — a missing updater config, no network,
 * or a user on an older Tauri without the plugin should NEVER prevent the
 * app from loading.
 */

interface TauriInvoker {
    core?: { invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> };
    invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
}
function tauriCore(): { invoke: TauriInvoker["core"] extends infer I ? (I extends { invoke: infer F } ? F : never) : never } | null {
    const t = (window as unknown as { __TAURI__?: TauriInvoker }).__TAURI__;
    if (!t) return null;
    if (t.core?.invoke) return { invoke: t.core.invoke };
    if (t.invoke) return { invoke: t.invoke };
    return null;
}

interface UpdateInfo {
    available?: boolean;
    version?: string;
    currentVersion?: string;
    body?: string;
    date?: string;
}

const update = ref<UpdateInfo | null>(null);
const downloading = ref(false);
const dismissed = ref(false);

async function checkForUpdate() {
    if (detectHost() !== "tauri") return;
    const core = tauriCore();
    if (!core) return;
    try {
        const result = await core.invoke("plugin:updater|check");
        if (result && typeof result === "object") {
            const r = result as Record<string, unknown>;
            if (r.available) {
                update.value = {
                    available: true,
                    version: String(r.version || ""),
                    currentVersion: String(r.currentVersion || ""),
                    body: String(r.body || ""),
                    date: String(r.date || ""),
                };
            }
        }
    } catch {
        // No updater configured, endpoint unreachable, signature check failed —
        // all surface as invoke errors. Silent: update is opt-in, not required.
    }
}

async function installAndRestart() {
    const core = tauriCore();
    if (!core) return;
    downloading.value = true;
    try {
        await core.invoke("plugin:updater|downloadAndInstall");
        showToast("下载完成，重启应用中…", "success", 2000);
        await core.invoke("plugin:process|restart");
    } catch (e) {
        downloading.value = false;
        showToast(`更新失败：${String((e as Error)?.message || e || "未知错误").slice(0, 120)}`, "error", 4000);
    }
}

onMounted(() => {
    // Delay 3s so the initial dashboard paint isn't competing with the
    // updater probe for CPU / network.
    setTimeout(() => void checkForUpdate(), 3000);
});
</script>

<template>
    <div
        v-if="update?.available && !dismissed"
        class="sticky top-0 z-[55] flex items-center justify-between gap-3 border-b border-brand-200/60 bg-brand-50/90 px-4 py-2 text-sm backdrop-blur-md dark:border-brand-900/50 dark:bg-brand-950/60"
    >
        <div class="flex items-center gap-2 text-brand-800 dark:text-brand-200">
            <Download class="h-4 w-4" aria-hidden="true" />
            <span>
                新版本 <span class="font-mono font-semibold">v{{ update.version }}</span> 可用
                <span v-if="update.currentVersion" class="opacity-70">（当前 v{{ update.currentVersion }}）</span>
            </span>
        </div>
        <div class="flex items-center gap-2">
            <Button size="sm" :disabled="downloading" :loading="downloading" variant="primary" @click="installAndRestart">
                <RefreshCw v-if="downloading" class="mr-1 h-3.5 w-3.5 animate-spin" />
                立即更新
            </Button>
            <Button size="sm" :disabled="downloading" @click="dismissed = true">稍后</Button>
        </div>
    </div>
</template>
