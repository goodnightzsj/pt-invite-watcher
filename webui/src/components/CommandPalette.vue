<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { Search, CornerDownLeft } from "lucide-vue-next";

import { allCommands, executeCommand, filterCommands, recentCommandIds, type CommandDef } from "../commands";

const open = ref(false);
const query = ref("");
const activeIndex = ref(0);
const inputRef = ref<HTMLInputElement | null>(null);

function openPalette() {
    open.value = true;
    query.value = "";
    activeIndex.value = 0;
    nextTick(() => inputRef.value?.focus());
}

function closePalette() {
    open.value = false;
    query.value = "";
}

/**
 * Shown commands: when no query, surface recent 5 first then the rest; with
 * a query, fuzzy-filter across everything. Keeps the palette useful on
 * first open (shows what the user just did) and on active typing.
 */
const displayed = computed<{ cmd: CommandDef; recent: boolean }[]>(() => {
    if (query.value.trim()) {
        return filterCommands(query.value).map((cmd) => ({ cmd, recent: false }));
    }
    const recent = recentCommandIds();
    const recentSet = new Set(recent);
    const all = allCommands();
    const byId = new Map(all.map((c) => [c.id, c]));
    const recentCmds = recent.map((id) => byId.get(id)).filter(Boolean) as CommandDef[];
    const rest = all.filter((c) => !recentSet.has(c.id));
    return [
        ...recentCmds.map((cmd) => ({ cmd, recent: true })),
        ...rest.map((cmd) => ({ cmd, recent: false })),
    ];
});

watch(displayed, () => { activeIndex.value = 0; });

function onKeyDown(e: KeyboardEvent) {
    if (!open.value) {
        // Cmd/Ctrl+K opens the palette — global shortcut intercepted here
        // rather than main.ts so the open/close state is component-local.
        // Alt+Shift variants pass through to the browser / OS.
        if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
            e.preventDefault();
            openPalette();
        }
        return;
    }
    if (e.key === "Escape") {
        e.preventDefault();
        closePalette();
        return;
    }
    if (e.key === "ArrowDown") {
        e.preventDefault();
        if (displayed.value.length) {
            activeIndex.value = Math.min(displayed.value.length - 1, activeIndex.value + 1);
            scrollActiveIntoView();
        }
        return;
    }
    if (e.key === "ArrowUp") {
        e.preventDefault();
        if (displayed.value.length) {
            activeIndex.value = Math.max(0, activeIndex.value - 1);
            scrollActiveIntoView();
        }
        return;
    }
    if (e.key === "Enter") {
        e.preventDefault();
        const pick = displayed.value[activeIndex.value]?.cmd;
        if (pick) {
            closePalette();
            void executeCommand(pick.id);
        }
    }
}

function scrollActiveIntoView() {
    nextTick(() => {
        const root = document.querySelector<HTMLElement>('[data-cmd-palette-list]');
        if (!root) return;
        const el = root.querySelector<HTMLElement>(`[data-index="${activeIndex.value}"]`);
        el?.scrollIntoView({ block: "nearest" });
    });
}

onMounted(() => window.addEventListener("keydown", onKeyDown));
onUnmounted(() => window.removeEventListener("keydown", onKeyDown));
</script>

<template>
    <teleport to="body">
        <div
            v-if="open"
            class="fixed inset-0 z-[70] flex items-start justify-center px-4 pt-[10vh] backdrop-blur-sm"
            @click.self="closePalette"
        >
            <!-- Dim background -->
            <div class="absolute inset-0 bg-slate-900/40 dark:bg-black/60" @click="closePalette" aria-hidden="true"></div>

            <div
                class="relative w-full max-w-xl overflow-hidden rounded-2xl border border-white/20 bg-white/95 shadow-2xl backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/95"
                role="dialog"
                aria-modal="true"
                aria-label="命令面板"
            >
                <div class="flex items-center gap-3 border-b border-slate-200/60 px-4 py-3 dark:border-slate-700/60">
                    <Search class="h-4 w-4 text-slate-400" aria-hidden="true" />
                    <input
                        ref="inputRef"
                        v-model="query"
                        type="text"
                        class="w-full appearance-none border-0 bg-transparent p-0 text-base text-slate-900 outline-none placeholder:text-slate-400 dark:text-slate-100"
                        placeholder="输入命令或搜索（Esc 关闭）"
                        autocomplete="off"
                        autocorrect="off"
                        spellcheck="false"
                    />
                    <span class="hidden shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-300 sm:inline">⌘K</span>
                </div>

                <div
                    data-cmd-palette-list
                    class="max-h-[50vh] overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/60"
                >
                    <div v-if="!displayed.length" class="px-4 py-10 text-center text-sm text-slate-400">
                        没有匹配的命令
                    </div>
                    <button
                        v-for="(row, index) in displayed"
                        :key="row.cmd.id"
                        :data-index="index"
                        type="button"
                        class="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-sm transition-colors"
                        :class="index === activeIndex
                            ? 'bg-brand-50 dark:bg-brand-500/10'
                            : 'hover:bg-slate-50 dark:hover:bg-slate-900'"
                        @mouseenter="activeIndex = index"
                        @click="() => { closePalette(); executeCommand(row.cmd.id); }"
                    >
                        <div class="flex min-w-0 flex-1 items-center gap-3">
                            <span class="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800/70 dark:text-slate-300">
                                {{ row.recent ? "最近" : row.cmd.category }}
                            </span>
                            <span class="truncate text-slate-900 dark:text-slate-100">{{ row.cmd.label }}</span>
                        </div>
                        <div class="flex shrink-0 items-center gap-2">
                            <span v-if="row.cmd.shortcut" class="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 dark:bg-slate-800/70 dark:text-slate-300">
                                {{ row.cmd.shortcut }}
                            </span>
                            <CornerDownLeft v-if="index === activeIndex" class="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                        </div>
                    </button>
                </div>

                <div class="border-t border-slate-100 bg-slate-50/50 px-4 py-2 text-[11px] text-slate-400 dark:border-slate-800/60 dark:bg-slate-900/40">
                    <kbd class="rounded bg-slate-200 px-1 font-mono dark:bg-slate-700">↑</kbd>
                    <kbd class="ml-1 rounded bg-slate-200 px-1 font-mono dark:bg-slate-700">↓</kbd>
                    导航 ·
                    <kbd class="rounded bg-slate-200 px-1 font-mono dark:bg-slate-700">Enter</kbd>
                    执行 ·
                    <kbd class="rounded bg-slate-200 px-1 font-mono dark:bg-slate-700">Esc</kbd>
                    关闭
                </div>
            </div>
        </div>
    </teleport>
</template>
