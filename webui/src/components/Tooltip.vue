<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from "vue";

const props = withDefaults(
    defineProps<{
        text?: string | null;
        delay?: number;
        maxWidth?: number;
        disabled?: boolean;
    }>(),
    {
        delay: 250,
        maxWidth: 320,
        disabled: false,
    }
);

type Placement = "top" | "bottom";

const open = ref(false);
const placement = ref<Placement>("top");
const anchorRef = ref<HTMLElement | null>(null);
const tipRef = ref<HTMLElement | null>(null);
const tipStyle = ref<Record<string, string>>({});

let showTimer: number | undefined;

const visibleText = computed(() => (props.text || "").toString().trim());
const canShow = computed(() => !props.disabled && visibleText.value.length > 0);

function clearShowTimer() {
    if (showTimer != null) {
        window.clearTimeout(showTimer);
        showTimer = undefined;
    }
}

function updatePosition() {
    const anchor = anchorRef.value;
    const tip = tipRef.value;
    if (!anchor || !tip) return;

    const rect = anchor.getBoundingClientRect();
    const tipRect = tip.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const margin = 6;
    const gap = 8;

    // Prefer `top` but flip to `bottom` when there isn't enough room above.
    const roomAbove = rect.top;
    const roomBelow = vh - rect.bottom;
    const preferred: Placement = roomAbove < tipRect.height + gap + margin && roomBelow > roomAbove ? "bottom" : "top";
    placement.value = preferred;

    const topPx =
        preferred === "top"
            ? Math.max(margin, rect.top - tipRect.height - gap)
            : Math.min(vh - tipRect.height - margin, rect.bottom + gap);

    const centerX = rect.left + rect.width / 2;
    let leftPx = centerX - tipRect.width / 2;
    leftPx = Math.max(margin, Math.min(vw - tipRect.width - margin, leftPx));

    tipStyle.value = {
        position: "fixed",
        top: `${Math.round(topPx)}px`,
        left: `${Math.round(leftPx)}px`,
        maxWidth: `${props.maxWidth}px`,
        zIndex: "70",
    };
}

async function show(event: Event) {
    if (!canShow.value) return;
    if (event.target instanceof Element) {
        anchorRef.value = event.currentTarget as HTMLElement;
    }
    clearShowTimer();
    showTimer = window.setTimeout(async () => {
        open.value = true;
        await nextTick();
        updatePosition();
    }, Math.max(0, props.delay | 0));
}

function hide() {
    clearShowTimer();
    if (!open.value) return;
    open.value = false;
}

function onScroll() {
    if (!open.value) return;
    // On any scroll/resize the anchor moves; recompute or hide.
    updatePosition();
}

function onResize() {
    if (!open.value) return;
    updatePosition();
}

onBeforeUnmount(() => {
    clearShowTimer();
    window.removeEventListener("scroll", onScroll, true);
    window.removeEventListener("resize", onResize);
});

function onEnter(e: Event) {
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    show(e);
}

function onLeave() {
    hide();
    window.removeEventListener("scroll", onScroll, true);
    window.removeEventListener("resize", onResize);
}

function onFocus(e: Event) {
    show(e);
}

function onBlur() {
    hide();
}
</script>

<template>
    <span
        class="relative inline-flex"
        @mouseenter="onEnter"
        @mouseleave="onLeave"
        @focusin="onFocus"
        @focusout="onBlur"
    >
        <slot />

        <teleport to="body">
            <transition
                enter-active-class="transition duration-150 ease-out"
                enter-from-class="opacity-0 translate-y-1"
                enter-to-class="opacity-100 translate-y-0"
                leave-active-class="transition duration-100 ease-in"
                leave-from-class="opacity-100 translate-y-0"
                leave-to-class="opacity-0 translate-y-1"
            >
                <div
                    v-if="open && canShow"
                    ref="tipRef"
                    :style="tipStyle"
                    role="tooltip"
                    class="pointer-events-none select-text whitespace-pre-wrap break-words rounded-lg border border-slate-200/60 bg-slate-900/95 px-3 py-2 text-xs font-medium leading-snug text-white shadow-xl backdrop-blur-md dark:border-white/10 dark:bg-slate-800/95"
                >
                    {{ visibleText }}
                    <span
                        aria-hidden="true"
                        class="absolute left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 bg-slate-900/95 dark:bg-slate-800/95"
                        :style="placement === 'top' ? { bottom: '-4px' } : { top: '-4px' }"
                    />
                </div>
            </transition>
        </teleport>
    </span>
</template>
