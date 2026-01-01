<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";

import Badge from "../components/Badge.vue";
import SiteIcon from "../components/SiteIcon.vue";
import PageHeader from "../components/PageHeader.vue";
import Button from "../components/Button.vue";
import Modal from "../components/Modal.vue";
import EmptyState from "../components/EmptyState.vue";
import FormInput from "../components/FormInput.vue";
import SiteCard from "../components/SiteCard.vue";
import { api, type SiteConfigItem, type SiteTemplate } from "../api";
import { showToast } from "../toast";

type EditMode = "manual" | "override";

type FormModel = {
  mode: EditMode;
  source: "moviepilot" | "manual";
  domain: string;
  url: string;
  name: string;
  template: SiteTemplate;
  registration_url: string;
  invite_url: string;
  cookie: string;
  clear_cookie: boolean;
  cookie_configured: boolean;
  authorization: string;
  clear_authorization: boolean;
  authorization_configured: boolean;
  did: string;
  clear_did: boolean;
  did_configured: boolean;
};

const loading = ref(false);
const saving = ref(false);
const items = ref<SiteConfigItem[]>([]);
const moviepilotOk = ref(false);
const moviepilotError = ref("");

const modalOpen = ref(false);
const modalTitle = ref("");
const form = reactive<FormModel>({
  mode: "manual",
  source: "manual",
  domain: "",
  url: "",
  name: "",
  template: "nexusphp",
  registration_url: "",
  invite_url: "",
  cookie: "",
  clear_cookie: false,
  cookie_configured: false,
  authorization: "",
  clear_authorization: false,
  authorization_configured: false,
  did: "",
  clear_did: false,
  did_configured: false,
});

function resetForm() {
  form.mode = "manual";
  form.source = "manual";
  form.domain = "";
  form.url = "";
  form.name = "";
  form.template = "nexusphp";
  form.registration_url = "";
  form.invite_url = "";
  form.cookie = "";
  form.clear_cookie = false;
  form.cookie_configured = false;
  form.authorization = "";
  form.clear_authorization = false;
  form.authorization_configured = false;
  form.did = "";
  form.clear_did = false;
  form.did_configured = false;
}

function parseDomainFromUrl(url: string) {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}



const computedDomain = computed(() => (form.domain || parseDomainFromUrl(form.url)).trim().toLowerCase());
const isCustom = computed(() => form.template === "custom");
const isMteam = computed(() => form.template === "mteam");

function displayPath(url: string) {
  try {
    const u = new URL(url);
    const path = (u.pathname || "/").replace(/^\/+/, "") || "/";
    return `${path}${u.search || ""}`;
  } catch {
    return url;
  }
}

function displayInvitePath(item: SiteConfigItem) {
  if (!item.invite_url) return "-";
  return displayPath(item.invite_url);
}

watch(
  () => form.template,
  (tpl) => {
    if (tpl !== "custom") {
      form.registration_url = "";
      form.invite_url = "";
    }
  }
);

async function load(opts: { toast?: boolean } = {}) {
  loading.value = true;
  try {
    const data = await api.sitesList();
    items.value = data.items || [];
    moviepilotOk.value = !!data.moviepilot_ok;
    moviepilotError.value = data.moviepilot_error || "";
    if (opts.toast) showToast("列表已更新", "success", 1800);
  } catch (e: any) {
    showToast(String(e?.message || e || "加载失败"), "error");
  } finally {
    loading.value = false;
  }
}

async function reload() {
  if (loading.value) return;
  showToast("正在刷新列表…", "info", 1600);
  await load({ toast: true });
}

function openAdd() {
  resetForm();
  modalTitle.value = "新增站点";
  modalOpen.value = true;
}

function openEdit(item: SiteConfigItem) {
  resetForm();
  form.mode = item.source === "manual" ? "manual" : "override";
  form.source = item.source;
  form.domain = item.domain;
  form.url = item.url;
  form.name = item.name || "";
  form.template = item.template;
  form.cookie_configured = !!item.cookie_configured;
  form.authorization_configured = !!item.authorization_configured;
  form.did_configured = !!item.did_configured;
  if (item.template === "custom") {
    form.registration_url = item.registration_url || "";
    form.invite_url = item.invite_url || "";
  }
  modalTitle.value = item.source === "manual" ? "编辑站点" : "编辑覆盖";
  modalOpen.value = true;
}

async function save() {
  saving.value = true;
  try {
    showToast("正在保存…", "info", 1600);
    const payload: any = {
      mode: form.mode,
      domain: computedDomain.value || form.domain || undefined,
      name: form.name,
      template: form.template,
    };

    if (form.mode === "manual") {
      payload.url = form.url;
    }

    if (form.template === "custom") {
      payload.registration_url = form.registration_url;
      payload.invite_url = form.invite_url;
    }

    if (form.clear_cookie) {
      payload.clear_cookie = true;
    } else if (form.cookie.trim()) {
      payload.cookie = form.cookie.trim();
    }

    if (form.template === "mteam") {
      if (form.clear_authorization) {
        payload.clear_authorization = true;
      } else if (form.authorization.trim()) {
        payload.authorization = form.authorization.trim();
      }

      if (form.clear_did) {
        payload.clear_did = true;
      } else if (form.did.trim()) {
        payload.did = form.did.trim();
      }
    }

    const resp = await api.sitesUpsert(payload);
    if (resp?.scan_triggered) {
      showToast("已保存（只写入本服务），已触发单站扫描", "success", 2400);
    } else if (resp?.scan_reason === "already_scanning") {
      showToast("已保存（只写入本服务），该站点正在扫描中", "success", 2400);
    } else {
      showToast("已保存（只写入本服务）", "success", 2000);
    }
    modalOpen.value = false;
    await load();
  } catch (e: any) {
    showToast(String(e?.message || e || "保存失败"), "error", 4500);
  } finally {
    saving.value = false;
  }
}

import { confirm } from "../confirm";

async function remove(item: SiteConfigItem) {
  const label = item.source === "manual" ? "删除站点" : "清除覆盖";
  if (!(await confirm(`确认${label}：${item.name || item.domain} (${item.domain}) 吗？`))) return;

  try {
    await api.sitesDelete(item.domain);
    showToast(`${label}成功`, "success");
    await load();
  } catch (e: any) {
    showToast(String(e?.message || e || `${label}失败`), "error");
  }
}

function badgeForSource(source: string) {
  return source === "manual" ? { label: "manual", tone: "amber" } : { label: "moviepilot", tone: "slate" };
}

onMounted(() => load());
</script>

<template>
  <div class="space-y-5">
    <PageHeader title="站点管理">
      <template #description>
        <div class="mt-1 text-sm text-slate-500 dark:text-slate-400">
          手动新增/覆盖只写入本服务 SQLite，不会覆盖 MoviePilot。
        </div>
        <div v-if="moviepilotError" class="mt-2 text-xs font-medium text-danger-600 dark:text-danger-300">
           MoviePilot：{{ moviepilotOk ? "ok" : "fail" }} · {{ moviepilotError }}
        </div>
      </template>

      <template #actions>
          <div class="flex gap-2">
            <Button :disabled="loading" @click="reload" class="flex-1 sm:flex-none">
              刷新列表
            </Button>
            <Button variant="primary" @click="openAdd" class="flex-1 sm:flex-none">
              新增站点
            </Button>
          </div>
      </template>
    </PageHeader>

    <EmptyState v-if="items.length === 0 && !loading" title="暂无站点" description="请检查 MoviePilot 连接配置或手动添加站点" actionText="新增站点" @action="openAdd" />
    <EmptyState v-else-if="loading && items.length === 0" title="加载中" description="正在同步站点列表..." >
       <template #icon>
        <div class="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-brand-500 dark:border-slate-800 dark:border-t-brand-500" />
      </template>
    </EmptyState>

    <template v-else>
    <!-- Mobile Card View -->
    <div class="space-y-4 sm:hidden">
      <div v-for="(site, i) in items"
        :key="site.name"
        class="relative overflow-hidden rounded-xl bg-white p-4 shadow-sm transition-all active:scale-[0.98] dark:bg-slate-900/50 glass border border-slate-100 dark:border-slate-800"
      >
        <div class="flex items-start justify-between">
           <div class="flex items-center gap-3">
             <div class="h-10 w-10">
                <SiteIcon :url="site.url" :name="site.name || site.domain" />
             </div>
             <div>
                <div class="font-semibold text-slate-800 dark:text-slate-100">{{ site.name || site.domain }}</div>
                <div class="text-xs text-slate-400">{{ site.domain }}</div>
             </div>
           </div>
        </div>

        <div class="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500 dark:text-slate-400">
            <div>
               <span class="opacity-60">来源:</span> {{ site.source }}
            </div>
             <div>
               <span class="opacity-60">模板:</span> {{ site.template }}
            </div>
        </div>

        <div class="mt-3 flex items-center justify-end gap-2 border-t border-slate-50 pt-3 dark:border-slate-800/50">
           <Button v-if="site.source === 'manual' || site.has_local_config" variant="danger" size="sm" @click="remove(site)">删除</Button>
           <Button size="sm" @click="openEdit(site)">编辑</Button>
        </div>
      </div>
    </div>

    <!-- Desktop Table View -->
    <div class="hidden overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:block">
      <div class="border-b border-slate-100 px-4 py-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        共 {{ items.length }} 个站点（MoviePilot + 手动/覆盖）
      </div>

      <div class="overflow-x-auto">
        <table class="min-w-full text-left text-sm">
          <thead class="bg-slate-50 border-b border-slate-200/70 text-xs uppercase tracking-wider text-slate-500 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-400">
            <tr>
              <th class="px-6 py-4 font-semibold">站点</th>
              <th class="px-6 py-4 font-semibold">域名</th>
              <th class="px-6 py-4 font-semibold">来源</th>
              <th class="px-6 py-4 font-semibold">模板</th>
              <th class="px-6 py-4 font-semibold">Cookie</th>
              <th class="px-6 py-4 font-semibold">注册页</th>
              <th class="px-6 py-4 font-semibold">邀请页</th>
              <th class="px-6 py-4 font-semibold text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800/60">
             <TransitionGroup name="list" appear>
              <tr v-for="(item, index) in items" :key="item.domain" :style="{ '--i': index }" class="table-row-hover group transition-colors duration-150 hover:bg-slate-50/80 dark:hover:bg-slate-800/30">
                <td class="px-6 py-4 font-medium text-slate-700 dark:text-slate-200">
                  <div class="flex items-center gap-3">
                     <div class="h-8 w-8">
                        <SiteIcon :url="item.url" :name="item.name || '-'" />
                     </div>
                    <div class="flex flex-col">
                      <span>{{ item.name || "-" }}</span>
                      <Badge v-if="item.reachability_state === 'down'" label="异常" tone="red" />
                    </div>
                  </div>
                </td>
                <td class="px-6 py-4">
                  <a
                    class="text-xs text-brand-500 underline decoration-brand-200 underline-offset-4 hover:decoration-brand-500 hover:text-brand-600 dark:text-brand-400 dark:decoration-brand-900 dark:hover:decoration-brand-400 dark:hover:text-brand-300"
                    :href="item.url"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {{ item.domain }}
                  </a>
                  <div v-if="item.has_local_config && item.source === 'moviepilot'" class="mt-1 inline-flex items-center rounded bg-warning-50 px-1.5 py-0.5 text-[10px] font-medium text-warning-700 ring-1 ring-inset ring-warning-600/20 dark:bg-warning-900/40 dark:text-warning-300">
                    本地覆盖
                  </div>
                </td>
                <td class="px-6 py-4">
                  <Badge :label="badgeForSource(item.source).label" :tone="badgeForSource(item.source).tone as any" />
                </td>
                <td class="px-6 py-4">
                  <Badge :label="item.template" tone="slate" />
                </td>
                <td class="px-6 py-4">
                  <Badge :label="item.cookie_configured ? 'configured' : 'none'" :tone="item.cookie_configured ? 'green' : 'slate'" />
                </td>
                <td class="px-6 py-4">
                  <a
                    v-if="item.registration_url"
                    class="text-xs text-slate-500 hover:text-brand-600 dark:text-slate-400 dark:hover:text-brand-400"
                    :href="item.registration_url"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {{ displayPath(item.registration_url) }}
                  </a>
                  <span v-else class="text-xs text-slate-300 dark:text-slate-600">-</span>
                </td>
                <td class="px-6 py-4">
                  <a
                    v-if="item.invite_url"
                    class="text-xs text-slate-500 hover:text-brand-600 dark:text-slate-400 dark:hover:text-brand-400"
                    :href="item.invite_url"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {{ displayInvitePath(item) }}
                  </a>
                  <span v-else class="text-xs text-slate-300 dark:text-slate-600">-</span>
                </td>
                <td class="px-6 py-4 text-right">
                  <div class="flex items-center justify-end gap-2">
                    <button
                      class="whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                      @click="openEdit(item)"
                    >
                      编辑
                    </button>
                    <button
                      v-if="item.source === 'manual' || item.has_local_config"
                      class="whitespace-nowrap rounded-lg border border-danger-200 bg-danger-50 px-3 py-1.5 text-xs font-medium text-danger-700 shadow-sm hover:bg-danger-100 hover:text-danger-900 dark:border-danger-900/50 dark:bg-danger-950/30 dark:text-danger-400 dark:hover:bg-danger-900/50"
                      @click="remove(item)"
                    >
                      {{ item.source === "manual" ? "删除" : "清除覆盖" }}
                    </button>
                    <span v-else class="text-xs text-slate-300 dark:text-slate-600">-</span>
                  </div>
                </td>
              </tr>
            </TransitionGroup>
          </tbody>
        </table>
      </div>
    </div>
    </template>

    <Modal :open="modalOpen" :title="modalTitle" @close="modalOpen = false">
      <div class="space-y-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <FormInput label="Mode（模式）" :model-value="form.mode" disabled />
          <div>
            <FormInput label="Domain（域名，唯一键）" :model-value="computedDomain || '-'" disabled>
                <template #help>
                    <div v-if="form.mode === 'manual'" class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      手动站点：domain 默认从 URL 自动解析。
                    </div>
                </template>
            </FormInput>
          </div>
        </div>

        <div v-if="form.mode === 'manual'">
          <FormInput label="Site URL（站点地址）" v-model="form.url" placeholder="https://example.com" />
        </div>
        <div v-else>
           <FormInput label="Site URL（来自 MoviePilot，只读）" :model-value="form.url" disabled />
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <FormInput label="Name（站点名）" v-model="form.name" placeholder="可选" />
          <div>
            <label class="block text-sm font-medium">Template（模板）</label>
            <select v-model="form.template" class="mt-1 ui-select">
              <option value="nexusphp">nexusphp</option>
              <option value="custom">custom（自定义注册/邀请页）</option>
              <option value="mteam">m-team（馒头）</option>
            </select>
          </div>
        </div>

        <div v-if="isCustom" class="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
          <div class="mb-3 text-sm font-semibold">Custom URLs（用于解析 path）</div>
          <div class="space-y-3">
            <FormInput label="Registration URL（注册页链接）" v-model="form.registration_url" placeholder="https://kp.m-team.cc/signup" />
            <FormInput label="Invite URL（邀请页链接）" v-model="form.invite_url" placeholder="https://kp.m-team.cc/invite" />
            <div class="text-xs text-slate-500 dark:text-slate-400">
              将从 URL 中解析出页面路径（保留 query），用于后续检测。
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div class="text-sm font-semibold">Cookie（站点覆盖优先级最高）</div>
            <Badge :label="form.cookie_configured ? '已配置' : '未配置'" :tone="form.cookie_configured ? 'green' : 'amber'" />
          </div>
          <div class="space-y-3">
            <FormInput
              label="Cookie Header（留空不修改）"
              v-model="form.cookie"
              type="textarea"
              placeholder="uid=...; pass=...; ..."
              :disabled="form.clear_cookie"
            />
            <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
              <input v-model="form.clear_cookie" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-slate-900 dark:border-slate-700 dark:bg-slate-950" />
              清空 cookie（回退到 cookie.source）
            </label>
          </div>
        </div>

        <div
          v-if="isMteam"
          class="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40"
        >
          <div class="mb-3 flex items-center justify-between gap-3">
            <div class="text-sm font-semibold">API（仅用于 m-team）</div>
            <div class="flex flex-wrap gap-2">
              <Badge :label="form.authorization_configured ? 'Authorization 已配置' : 'Authorization 未配置'" :tone="form.authorization_configured ? 'green' : 'amber'" />
              <Badge :label="form.did_configured ? 'API Key 已配置' : 'API Key 未配置'" :tone="form.did_configured ? 'green' : 'amber'" />
            </div>
          </div>
          <div class="space-y-3">

            <FormInput
              label="Authorization（留空不修改）"
              v-model="form.authorization"
              type="textarea"
              placeholder="eyJhbGciOiJIUzUxMiJ9..."
              :disabled="form.clear_authorization"
            />
            <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
              <input
                v-model="form.clear_authorization"
                type="checkbox"
                class="h-4 w-4 rounded border-slate-300 text-slate-900 dark:border-slate-700 dark:bg-slate-950"
              />
              清空 Authorization
            </label>

            <FormInput label="API Key（did，留空不修改）" v-model="form.did" placeholder="63788714-a1fa-..." :disabled="form.clear_did" />
            <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
              <input v-model="form.clear_did" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-slate-900 dark:border-slate-700 dark:bg-slate-950" />
              清空 API Key
            </label>
          </div>
        </div>

        <div class="flex flex-wrap justify-end gap-3">
          <Button :disabled="saving" @click="modalOpen = false">取消</Button>
          <Button variant="primary" :disabled="saving" @click="save">保存</Button>
        </div>
      </div>
    </Modal>
  </div>
</template>
