<script setup lang="ts">
import { computed } from "vue";
import Tooltip from "./Tooltip.vue";
import { formatLocalTime, formatRelativeTime } from "../utils/date";

/**
 * Display relative time ("5 分钟前") with an absolute time tooltip on hover.
 *
 * Relative time is what users actually want at a glance ("how stale is this?")
 * but when they need to reason about exact timing — "was this before or after
 * the deploy at 15:00?" — they're forced to mentally convert. Pairing both in
 * one atom removes that friction without cluttering the layout.
 *
 * The tooltip also surfaces which timezone the absolute value is in via the
 * browser's IANA resolver, so users who travel / share screenshots get
 * unambiguous timestamps.
 */
const props = defineProps<{
    ts: string | null | undefined;
    // When true, render without wrapping in a span (useful inside <div> flex items
    // where an extra span would break layout). Default false.
    inline?: boolean;
}>();

const relative = computed(() => formatRelativeTime(props.ts));
const absolute = computed(() => formatLocalTime(props.ts));

const tzLabel = computed(() => {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch {
        return "";
    }
});

const tooltipText = computed(() => {
    if (!props.ts) return "";
    const tz = tzLabel.value;
    return tz ? `${absolute.value}  (${tz})` : absolute.value;
});
</script>

<template>
    <Tooltip v-if="ts" :text="tooltipText">
        <span :class="props.inline ? '' : 'cursor-help'">{{ relative }}</span>
    </Tooltip>
    <span v-else>{{ relative }}</span>
</template>
