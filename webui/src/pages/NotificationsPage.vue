<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import Badge from "../components/Badge.vue";
import Toggle from "../components/Toggle.vue";
import { api, type NotificationsResponse } from "../api";
import { showToast } from "../toast";

type Model = {
  telegram: { enabled: boolean; token: string; chat_id: string };
  wecom: { enabled: boolean; corpid: string; app_secret: string; agent_id: string; to_user: string; to_party: string; to_tag: string };
};

const view = ref<NotificationsResponse | null>(null);
const loading = ref(false);
const saving = ref(false);
const testing = ref<"" | "telegram" | "wecom">("");

const model = reactive<Model>({
  telegram: { enabled: false, token: "", chat_id: "" },
  wecom: { enabled: false, corpid: "", app_secret: "", agent_id: "", to_user: "@all", to_party: "", to_tag: "" },
});

async function load() {
  loading.value = true;
  try {
    const data = await api.notificationsGet();
    view.value = data;
    model.telegram.enabled = !!data.telegram.enabled;
    model.telegram.token = "";
    model.telegram.chat_id = data.telegram.chat_id || "";

    model.wecom.enabled = !!data.wecom.enabled;
    model.wecom.corpid = data.wecom.corpid || "";
    model.wecom.app_secret = "";
    model.wecom.agent_id = data.wecom.agent_id || "";
    model.wecom.to_user = data.wecom.to_user || "@all";
    model.wecom.to_party = data.wecom.to_party || "";
    model.wecom.to_tag = data.wecom.to_tag || "";
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
      telegram: {
        enabled: model.telegram.enabled,
        chat_id: model.telegram.chat_id,
      },
      wecom: {
        enabled: model.wecom.enabled,
        corpid: model.wecom.corpid,
        agent_id: model.wecom.agent_id,
        to_user: model.wecom.to_user,
        to_party: model.wecom.to_party,
        to_tag: model.wecom.to_tag,
      },
    };
    if (model.telegram.token.trim()) payload.telegram.token = model.telegram.token.trim();
    if (model.wecom.app_secret.trim()) payload.wecom.app_secret = model.wecom.app_secret.trim();

    await api.notificationsPut(payload);
    showToast("已保存", "success");
    await load();
  } catch (e: any) {
    showToast(String(e?.message || e || "保存失败"), "error");
  } finally {
    saving.value = false;
  }
}

async function test(channel: "telegram" | "wecom") {
  testing.value = channel;
  try {
    const res = await api.notificationsTest(channel);
    showToast(res.ok ? `测试成功：${res.message || "ok"}` : `测试失败：${res.message || "fail"}`, res.ok ? "success" : "error", 3500);
  } catch (e: any) {
    showToast(String(e?.message || e || "测试失败"), "error", 3500);
  } finally {
    testing.value = "";
  }
}

onMounted(() => load());
</script>

<template>
  <div class="space-y-5">
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-base font-semibold">通知设置</div>
          <div class="mt-1 text-sm text-slate-500 dark:text-slate-400">敏感信息会存储在本服务的 SQLite；建议为 Web UI 配置 BasicAuth 或放到内网。</div>
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
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="mb-4 flex items-center justify-between">
          <div class="text-sm font-semibold">Telegram</div>
          <Badge v-if="view" :label="view.telegram.configured ? '已配置' : '未配置'" :tone="view.telegram.configured ? 'green' : 'amber'" />
        </div>
        <div class="space-y-4">
          <div class="flex items-center gap-3">
            <Toggle v-model="model.telegram.enabled" />
            <div class="text-sm text-slate-700 dark:text-slate-200">启用 Telegram</div>
          </div>
          <div>
            <label class="block text-sm font-medium">Bot Token（留空不修改）</label>
            <input v-model="model.telegram.token" type="password" class="mt-1 ui-input" :placeholder="view?.telegram.configured ? '已配置' : '未配置'" />
          </div>
          <div>
            <label class="block text-sm font-medium">Chat ID</label>
            <input v-model="model.telegram.chat_id" type="text" class="mt-1 ui-input" placeholder="123456789" />
          </div>
          <button
            class="w-full rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            :disabled="testing !== ''"
            @click="test('telegram')"
          >
            {{ testing === 'telegram' ? '测试中…' : '测试 Telegram' }}
          </button>
        </div>
      </div>

      <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="mb-4 flex items-center justify-between">
          <div class="text-sm font-semibold">企业微信（企业应用）</div>
          <Badge v-if="view" :label="view.wecom.configured ? '已配置' : '未配置'" :tone="view.wecom.configured ? 'green' : 'amber'" />
        </div>
        <div class="space-y-4">
          <div class="flex items-center gap-3">
            <Toggle v-model="model.wecom.enabled" />
            <div class="text-sm text-slate-700 dark:text-slate-200">启用 企业微信</div>
          </div>
          <div>
            <label class="block text-sm font-medium">CorpID</label>
            <input v-model="model.wecom.corpid" type="text" class="mt-1 ui-input" placeholder="wwxxxx" />
          </div>
          <div>
            <label class="block text-sm font-medium">AppSecret（留空不修改）</label>
            <input v-model="model.wecom.app_secret" type="password" class="mt-1 ui-input" :placeholder="view?.wecom.configured ? '已配置' : '未配置'" />
          </div>
          <div>
            <label class="block text-sm font-medium">AgentID</label>
            <input v-model="model.wecom.agent_id" type="text" class="mt-1 ui-input" placeholder="1000002" />
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <label class="block text-sm font-medium">ToUser</label>
              <input v-model="model.wecom.to_user" type="text" class="mt-1 ui-input" placeholder="@all" />
            </div>
            <div>
              <label class="block text-sm font-medium">ToParty</label>
              <input v-model="model.wecom.to_party" type="text" class="mt-1 ui-input" placeholder="" />
            </div>
            <div>
              <label class="block text-sm font-medium">ToTag</label>
              <input v-model="model.wecom.to_tag" type="text" class="mt-1 ui-input" placeholder="" />
            </div>
          </div>
          <button
            class="w-full rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            :disabled="testing !== ''"
            @click="test('wecom')"
          >
            {{ testing === 'wecom' ? '测试中…' : '测试 企业微信' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
