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

    // Fallback to simple date string YYYY-MM-DD
    return date.toISOString().split("T")[0];
}
