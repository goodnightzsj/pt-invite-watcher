const _localFmt = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
});

/**
 * Absolute local-timezone timestamp with second precision.
 *
 * Converts ISO 8601 (the backend emits UTC like 2026-04-22T11:24:28.877440+00:00)
 * into a locale-aware string such as "2026/04/22 19:24:28" using the user's own
 * timezone. Used wherever we previously displayed raw ISO — raw UTC confuses
 * users who aren't on UTC and the sub-second component just adds visual noise.
 */
export function formatLocalTime(ts: string | null | undefined): string {
    if (!ts) return "-";
    const date = new Date(ts);
    if (Number.isNaN(date.getTime())) return String(ts);
    return _localFmt.format(date).replace(/\//g, "-");
}

export function formatRelativeTime(ts: string | null | undefined): string {
    if (!ts) return "-";
    const date = new Date(ts);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);

    // Less than 1 minute
    if (diffSec < 60) {
        return "刚刚";
    }

    // Less than 1 hour
    if (diffSec < 3600) {
        const mins = Math.floor(diffSec / 60);
        return `${mins}分钟前`;
    }

    // Less than 24 hours
    if (diffSec < 86400) {
        const hours = Math.floor(diffSec / 3600);
        return `${hours}小时前`;
    }

    // Less than 7 days
    if (diffSec < 604800) {
        const days = Math.floor(diffSec / 86400);
        return `${days}天前`;
    }

    // Fallback to local-timezone date so users on non-UTC locales see sensible output.
    return formatLocalTime(ts);
}
