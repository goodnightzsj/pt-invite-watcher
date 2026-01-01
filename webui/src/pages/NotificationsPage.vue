<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import Badge from "../components/Badge.vue";
import Toggle from "../components/Toggle.vue";
import Card from "../components/Card.vue";
import Button from "../components/Button.vue";
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
const baselineJson = ref<string>("");

const model = reactive<Model>({
  telegram: { enabled: false, token: "", chat_id: "" },
  wecom: { enabled: false, corpid: "", app_secret: "", agent_id: "", to_user: "@all", to_party: "", to_tag: "" },
});

function _normStr(v: string) {
  return (v || "").trim();
}

function normalizedModelForCompare(m: Model) {
  return {
    telegram: {
      enabled: Boolean(m.telegram.enabled),
      token: _normStr(m.telegram.token),
      chat_id: _normStr(m.telegram.chat_id),
    },
    wecom: {
      enabled: Boolean(m.wecom.enabled),
      corpid: _normStr(m.wecom.corpid),
      app_secret: _normStr(m.wecom.app_secret),
      agent_id: _normStr(m.wecom.agent_id),
      to_user: _normStr(m.wecom.to_user),
      to_party: _normStr(m.wecom.to_party),
      to_tag: _normStr(m.wecom.to_tag),
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
  baselineJson.value = "";
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
  if (!isDirty.value) return;
  saving.value = true;
  try {
    showToast("正在保存…", "info", 1600);
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
    showToast(`正在测试：${channel}`, "info", 1600);
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
    <Card>
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-base font-semibold">通知设置</div>
          <div class="mt-1 text-sm text-slate-500 dark:text-slate-400">敏感信息会存储在本服务的 SQLite；建议为 Web UI 配置 BasicAuth 或放到内网。</div>
        </div>
        <div class="flex items-center gap-3">
          <Button :disabled="loading" :loading="loading" @click="reload">重新加载</Button>
          <Button variant="primary" :disabled="saving || !isDirty" :loading="saving" @click="save">保存</Button>
        </div>
      </div>
    </Card>

    <div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <Card>
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
          <Button
            class="w-full"
            :disabled="testing !== ''"
            :loading="testing === 'telegram'"
            @click="test('telegram')"
          >
            测试 Telegram
          </Button>
        </div>
      </Card>

      <Card>
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
          <Button
            class="w-full"
            :disabled="testing !== ''"
            :loading="testing === 'wecom'"
            @click="test('wecom')"
          >
            测试 企业微信
          </Button>
        </div>
      </Card>
    </div>
  </div>
</template>
