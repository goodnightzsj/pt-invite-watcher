import { ref } from "vue";

/**
 * Browser desktop notifications for in-page state changes.
 *
 * This is layered ON TOP OF the server-side Telegram / 企业微信 notifications —
 * those reach the user when the dashboard isn't open at all; this module is
 * for the case where the dashboard IS open in a background tab and the user
 * wants their OS to surface a change without them having to click back to it.
 *
 * Storage model:
 * - `ptiw_browser_notifications_enabled` (localStorage) = user opt-in flag
 * - `Notification.permission` = browser-level grant (required on top of opt-in)
 * - In-memory `lastNotifiedAt` map debounces per-domain notifications to at
 *   most once every 30 minutes so we never flood the user when the server
 *   burst-scans many sites in quick succession.
 */
const STORAGE_KEY = "ptiw_browser_notifications_enabled";
const NOTIFY_DEBOUNCE_MS = 30 * 60 * 1000;
const _lastNotifiedAt = new Map<string, number>();

export const browserNotificationsEnabled = ref<boolean>(readEnabled());

function readEnabled(): boolean {
    try {
        return localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
        return false;
    }
}

function writeEnabled(v: boolean): void {
    try {
        localStorage.setItem(STORAGE_KEY, v ? "1" : "0");
    } catch {
        /* private mode — ignore */
    }
}

export function browserNotificationsSupported(): boolean {
    return typeof window !== "undefined" && "Notification" in window;
}

export function browserNotificationsPermission(): NotificationPermission | "unsupported" {
    if (!browserNotificationsSupported()) return "unsupported";
    return Notification.permission;
}

/**
 * Ask the browser for permission, then persist the user's opt-in flag.
 * Returns the resulting permission state.
 */
export async function enableBrowserNotifications(): Promise<NotificationPermission | "unsupported"> {
    if (!browserNotificationsSupported()) return "unsupported";
    const current = Notification.permission;
    const perm = current === "default" ? await Notification.requestPermission() : current;
    const ok = perm === "granted";
    browserNotificationsEnabled.value = ok;
    writeEnabled(ok);
    return perm;
}

export function disableBrowserNotifications(): void {
    browserNotificationsEnabled.value = false;
    writeEnabled(false);
}

/**
 * Fire a native notification, respecting both the opt-in flag and the per-key
 * debounce window. `key` is typically the site domain; duplicates within
 * `NOTIFY_DEBOUNCE_MS` are silently dropped so the user isn't spammed when
 * the scanner emits multiple rapid updates for the same site.
 */
export function notifyBrowser(
    key: string,
    title: string,
    body: string,
    options: { url?: string; icon?: string } = {}
): void {
    if (!browserNotificationsEnabled.value) return;
    if (!browserNotificationsSupported()) return;
    if (Notification.permission !== "granted") return;

    const now = Date.now();
    const last = _lastNotifiedAt.get(key) || 0;
    if (now - last < NOTIFY_DEBOUNCE_MS) return;
    _lastNotifiedAt.set(key, now);

    try {
        const n = new Notification(title, {
            body,
            icon: options.icon,
            tag: `ptiw-${key}`,           // same tag → subsequent notifications replace
            renotify: false,               // but don't re-alert if OS already showed it
        });
        if (options.url) {
            n.onclick = () => {
                try {
                    window.focus();
                    window.open(options.url, "_blank", "noopener,noreferrer");
                } catch {
                    /* no-op */
                }
            };
        }
    } catch {
        /* browsers rate-limit / reject invalid options — not fatal */
    }
}
