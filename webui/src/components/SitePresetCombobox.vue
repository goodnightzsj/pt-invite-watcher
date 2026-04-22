<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import { ChevronDown, Search, X } from "lucide-vue-next";
import type { RegistrySite } from "../api";

const props = withDefaults(
    defineProps<{
        options: RegistrySite[];
        modelValue?: string;
        placeholder?: string;
        disabled?: boolean;
    }>(),
    {
        modelValue: "",
        placeholder: "搜索已知站点：名称 / 域名 / 别名",
        disabled: false,
    }
);

const emit = defineEmits<{
    (e: "update:modelValue", value: string): void;
    (e: "select", site: RegistrySite | null): void;
}>();

const open = ref(false);
const query = ref("");
const activeIndex = ref(0);
const triggerRef = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLInputElement | null>(null);
const panelRef = ref<HTMLElement | null>(null);
const panelStyle = ref<Record<string, string>>({});

const selected = computed(() => {
    if (!props.modelValue) return null;
    return props.options.find((o) => o.id === props.modelValue) || null;
});

function normalize(text: string) {
    return (text || "").toLowerCase().trim();
}

const filtered = computed(() => {
    const q = normalize(query.value);
    if (!q) return props.options;
    const tokens = q.split(/\s+/).filter(Boolean);
    return props.options.filter((site) => {
        const haystack = [
            site.id,
            site.name,
            site.primary_domain,
            ...(site.aliases || []),
            ...(site.domains || []),
            ...(site.tags || []),
        ]
            .map(normalize)
            .join(" ");
        return tokens.every((t) => haystack.includes(t));
    });
});

watch(filtered, () => {
    activeIndex.value = 0;
});

function updatePosition() {
    const el = triggerRef.value;
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const margin = 8;
    const width = rect.width;
    const vh = window.innerHeight;
    const vw = window.innerWidth;

    const spaceBelow = Math.max(0, vh - rect.bottom - margin);
    const spaceAbove = Math.max(0, rect.top - margin);
    const preferred = Math.min(360, Math.max(200, vh - margin * 2));
    const placeAbove = spaceBelow < Math.min(preferred, 240) && spaceAbove > spaceBelow;
    const available = placeAbove ? spaceAbove : spaceBelow;
    const maxHeight = Math.max(180, Math.min(preferred, available || preferred));

    let left = rect.left;
    const maxLeft = vw - margin - width;
    if (left > maxLeft) left = Math.max(margin, maxLeft);
    if (left < margin) left = margin;

    const top = placeAbove
        ? Math.max(margin, rect.top - margin - maxHeight)
        : Math.min(vh - margin - maxHeight, rect.bottom + margin);

    panelStyle.value = {
        position: "fixed",
        left: `${Math.round(left)}px`,
        top: `${Math.round(top)}px`,
        width: `${Math.round(width)}px`,
        maxHeight: `${Math.round(maxHeight)}px`,
        zIndex: "60",
    };
}

function onPointerDown(e: PointerEvent) {
    const target = e.target as Node | null;
    if (!target) return;
    if (triggerRef.value?.contains(target)) return;
    if (panelRef.value?.contains(target)) return;
    closePicker();
}

function onKeyDown(e: KeyboardEvent) {
    if (!open.value) return;
    if (e.key === "Escape") {
        e.preventDefault();
        closePicker();
        return;
    }
    if (e.key === "ArrowDown") {
        e.preventDefault();
        if (filtered.value.length === 0) return;
        activeIndex.value = Math.min(filtered.value.length - 1, activeIndex.value + 1);
        scrollActiveIntoView();
    } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (filtered.value.length === 0) return;
        activeIndex.value = Math.max(0, activeIndex.value - 1);
        scrollActiveIntoView();
    } else if (e.key === "Enter") {
        e.preventDefault();
        const item = filtered.value[activeIndex.value];
        if (item) pick(item);
    }
}

function scrollActiveIntoView() {
    const panel = panelRef.value;
    if (!panel) return;
    const el = panel.querySelector<HTMLElement>(`[data-index="${activeIndex.value}"]`);
    if (el) el.scrollIntoView({ block: "nearest" });
}

function onViewportChange() {
    if (!open.value) return;
    updatePosition();
}

function setupGlobalListeners() {
    document.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", onViewportChange);
    window.addEventListener("scroll", onViewportChange, true);
}

function teardownGlobalListeners() {
    document.removeEventListener("pointerdown", onPointerDown, true);
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("resize", onViewportChange);
    window.removeEventListener("scroll", onViewportChange, true);
}

async function openPicker(e?: MouseEvent) {
    if (props.disabled) return;
    if (open.value) {
        // Toggle behavior: a second click on the trigger closes the panel —
        // mirrors native <select> expectations while still being fully
        // keyboard-navigable.
        closePicker();
        // Mouse-driven close drops focus to avoid a focus-ring flash on the
        // trigger right as the panel disappears. Keyboard toggles (Enter/Space
        // produce detail === 0) keep focus for continued navigation.
        if (e && e.detail > 0) triggerRef.value?.blur();
        return;
    }
    open.value = true;
    setupGlobalListeners();
    await nextTick();
    updatePosition();
    inputRef.value?.focus();
}

function closePicker() {
    if (!open.value) return;
    open.value = false;
    teardownGlobalListeners();
}

function pick(site: RegistrySite | null) {
    if (!site) {
        emit("update:modelValue", "");
        emit("select", null);
    } else {
        emit("update:modelValue", site.id);
        emit("select", site);
    }
    query.value = "";
    closePicker();
}

function clearSelection(e: Event) {
    e.stopPropagation();
    pick(null);
}

onUnmounted(() => teardownGlobalListeners());

const triggerLabel = computed(() => {
    if (selected.value) return selected.value.name;
    return "— 手动填写 —";
});
</script>

<template>
    <div>
        <button
            ref="triggerRef"
            type="button"
            class="ui-input flex w-full items-center justify-between gap-2 text-left disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="props.disabled"
            @click="openPicker($event)"
            aria-haspopup="listbox"
            :aria-expanded="open ? 'true' : 'false'"
        >
            <span class="min-w-0 flex-1 truncate" :class="selected ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-300'">
                {{ triggerLabel }}
                <span v-if="selected" class="ml-2 text-xs text-slate-400">· {{ selected.primary_domain }}</span>
            </span>
            <span class="flex items-center gap-1">
                <button
                    v-if="selected"
                    type="button"
                    class="rounded p-0.5 text-slate-400 hover:bg-slate-200/60 hover:text-slate-700 dark:hover:bg-slate-700/60 dark:hover:text-slate-100"
                    aria-label="清除所选"
                    @click="clearSelection"
                >
                    <X class="h-3.5 w-3.5" />
                </button>
                <ChevronDown class="h-4 w-4 text-slate-500 dark:text-slate-300" aria-hidden="true" />
            </span>
        </button>

        <teleport to="body">
            <transition
                enter-active-class="transition duration-150 ease-out"
                enter-from-class="opacity-0 -translate-y-1 scale-95"
                enter-to-class="opacity-100 translate-y-0 scale-100"
                leave-active-class="transition duration-100 ease-in"
                leave-from-class="opacity-100 translate-y-0 scale-100"
                leave-to-class="opacity-0 -translate-y-1 scale-95"
            >
                <div
                    v-if="open"
                    ref="panelRef"
                    class="flex flex-col overflow-hidden rounded-xl border border-slate-200/60 bg-white/95 shadow-xl backdrop-blur-md dark:border-slate-700/60 dark:bg-slate-900/95"
                    :style="panelStyle"
                    role="listbox"
                >
                    <div class="border-b border-slate-100 p-2 dark:border-slate-800/60">
                        <label class="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-1.5 focus-within:border-brand-400 focus-within:bg-white focus-within:ring-2 focus-within:ring-brand-500/10 dark:border-slate-700/60 dark:bg-slate-800/40 dark:focus-within:border-brand-400 dark:focus-within:bg-slate-900/80">
                            <Search class="h-4 w-4 text-slate-400" aria-hidden="true" />
                            <input
                                ref="inputRef"
                                v-model="query"
                                type="text"
                                class="w-full bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none dark:text-slate-100"
                                :placeholder="props.placeholder"
                                @keydown.stop="onKeyDown"
                            />
                            <span class="shrink-0 text-xs text-slate-400 tabular-nums">{{ filtered.length }} / {{ options.length }}</span>
                        </label>
                    </div>

                    <div class="min-h-[60px] flex-1 overflow-auto divide-y divide-slate-100 dark:divide-slate-800/60">
                        <button
                            type="button"
                            class="flex w-full items-start gap-3 px-4 py-2.5 text-left text-xs text-slate-500 transition-colors hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-900"
                            @click="pick(null)"
                        >
                            — 不使用预设（手动填写）—
                        </button>
                        <button
                            v-for="(site, index) in filtered"
                            :key="site.id"
                            :data-index="index"
                            type="button"
                            class="flex w-full items-start gap-3 px-4 py-3 text-left text-sm transition-colors"
                            :class="[
                                index === activeIndex ? 'bg-brand-50 dark:bg-brand-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-900',
                                site.id === props.modelValue ? 'ring-1 ring-brand-300 dark:ring-brand-500/40' : '',
                            ]"
                            @mouseenter="activeIndex = index"
                            @click="pick(site)"
                        >
                            <div class="min-w-0 flex-1">
                                <div class="flex items-center gap-2">
                                    <span class="truncate font-medium text-slate-900 dark:text-slate-100">{{ site.name }}</span>
                                    <span
                                        v-for="t in site.tags.slice(0, 3)"
                                        :key="t"
                                        class="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800/70 dark:text-slate-300"
                                    >{{ t }}</span>
                                </div>
                                <div class="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
                                    {{ site.primary_domain }}
                                    <span v-if="site.aliases.length" class="ml-1 text-slate-400">· {{ site.aliases.join(" / ") }}</span>
                                </div>
                                <div v-if="site.notes" class="mt-0.5 truncate text-[11px] text-slate-400">
                                    {{ site.notes }}
                                </div>
                            </div>
                            <span class="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:bg-slate-800/70 dark:text-slate-300">
                                {{ site.schema }}
                            </span>
                        </button>

                        <div v-if="!filtered.length" class="px-4 py-6 text-center text-xs text-slate-400">
                            未匹配到站点。可直接在下方输入 URL 手动填写。
                        </div>
                    </div>
                </div>
            </transition>
        </teleport>
    </div>
</template>
