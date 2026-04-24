/**
 * Opportunistic integrations with the Capacitor runtime.
 *
 * When the bundle loads inside the Capacitor iOS/Android shell, `window.Capacitor`
 * is populated by the Capacitor runtime before our app boots. We detect that at
 * runtime and wire a few native niceties — no static import of `@capacitor/*`
 * packages so the browser + Tauri builds stay zero-dep and ship the same bundle.
 *
 * This file is best-effort. Every code path fails silently on browsers / Tauri
 * (where `window.Capacitor` is `undefined`) so mis-detection never crashes the
 * app.
 */
import type { Router } from "vue-router";

interface CapacitorPluginListener {
    remove?: () => void;
}

interface AppPlugin {
    addListener: (
        eventName: "backButton",
        listener: (event: { canGoBack?: boolean }) => void
    ) => Promise<CapacitorPluginListener>;
    exitApp: () => Promise<void>;
}

interface StatusBarPlugin {
    setStyle: (options: { style: "LIGHT" | "DARK" | "DEFAULT" }) => Promise<void>;
    setBackgroundColor: (options: { color: string }) => Promise<void>;
    setOverlaysWebView: (options: { overlay: boolean }) => Promise<void>;
}

interface HapticsPlugin {
    impact: (options: { style: "LIGHT" | "MEDIUM" | "HEAVY" }) => Promise<void>;
    selectionStart: () => Promise<void>;
    selectionChanged: () => Promise<void>;
    selectionEnd: () => Promise<void>;
}

interface PushPlugin {
    requestPermissions: () => Promise<{ receive: "granted" | "denied" | "prompt" }>;
    register: () => Promise<void>;
    addListener: (
        eventName: "registration" | "registrationError" | "pushNotificationReceived",
        handler: (data: unknown) => void
    ) => Promise<{ remove?: () => void }>;
}

interface CapacitorGlobal {
    getPlatform?: () => "web" | "ios" | "android";
    isNativePlatform?: () => boolean;
    Plugins?: {
        App?: AppPlugin;
        StatusBar?: StatusBarPlugin;
        Haptics?: HapticsPlugin;
        PushNotifications?: PushPlugin;
    };
}

function getCapacitor(): CapacitorGlobal | null {
    const cap = (window as unknown as { Capacitor?: CapacitorGlobal }).Capacitor;
    if (!cap) return null;
    if (cap.isNativePlatform && !cap.isNativePlatform()) return null;
    return cap;
}

/** True when loaded inside the Capacitor native shell (iOS or Android). */
export function isCapacitor(): boolean {
    return getCapacitor() !== null;
}

/** Platform string or "web" when not in Capacitor. */
export function capacitorPlatform(): "web" | "ios" | "android" {
    return getCapacitor()?.getPlatform?.() ?? "web";
}

/**
 * Detect the host shell so CSS / components can react per-platform.
 * Precedence: capacitor first (iOS / Android), then Tauri (desktop),
 * finally plain browser. Result is stable for the session.
 */
export type HostShell = "capacitor-ios" | "capacitor-android" | "tauri" | "browser";

export function detectHost(): HostShell {
    const plat = capacitorPlatform();
    if (plat === "ios") return "capacitor-ios";
    if (plat === "android") return "capacitor-android";
    const anyWin = window as unknown as { __TAURI__?: unknown; __TAURI_INTERNALS__?: unknown };
    if (anyWin.__TAURI__ || anyWin.__TAURI_INTERNALS__) return "tauri";
    return "browser";
}

/** Stamp the detected shell onto <html> so CSS can target via `[data-host="..."]`. */
export function applyHostAttribute(): void {
    document.documentElement.dataset.host = detectHost();
    // Additionally mark macOS Tauri so CSS can reserve horizontal space for
    // the traffic-light buttons without affecting Windows/Linux where the
    // shell either has no traffic lights or uses the right-side min/max/close.
    // navigator.platform is deprecated but still the shortest reliable hint
    // across WebKit + Chromium; userAgent mention of "Mac OS X" is the
    // standards-track fallback.
    const ua = navigator.userAgent || "";
    const isMac = /Mac OS X/i.test(ua) || /Macintosh/i.test(navigator.platform || "");
    if (isMac) {
        document.documentElement.dataset.os = "mac";
    }
}

/**
 * Fire a native haptic pulse — a tiny physical thud on iOS / Android that
 * confirms a tap landed where the user wanted. Graceful no-op on browser +
 * Tauri. `selection` is the lightest, used for list-item focus / filter-toggle
 * changes. `light` / `medium` correspond to iOS's UIImpactFeedbackGenerator
 * styles and roughly to Android's HapticFeedbackConstants equivalents.
 *
 * Keep usage sparse — overusing haptics makes the UI feel gimmicky; reserve
 * for confirming state changes users don't otherwise get immediate feedback
 * from (e.g. successful save, scan complete, filter applied).
 */
export function haptic(style: "light" | "medium" | "heavy" | "selection" = "light"): void {
    const h = getCapacitor()?.Plugins?.Haptics;
    if (!h) return;
    if (style === "selection") {
        h.selectionChanged().catch(() => { });
        return;
    }
    h.impact({ style: style.toUpperCase() as "LIGHT" | "MEDIUM" | "HEAVY" }).catch(() => { });
}

/**
 * Tauri autostart (launch at login) bridge — no-op on non-Tauri shells.
 *
 * `tauri-plugin-autostart` exposes itself via IPC at
 * `plugin:autostart|enable|disable|is_enabled`. Rather than adding
 * `@tauri-apps/plugin-autostart` to webui/package.json (which would leak
 * a Tauri dep into the browser + Capacitor builds), we call the core IPC
 * proxy directly — available under `window.__TAURI__.core.invoke` when
 * `withGlobalTauri: true` is set in tauri.conf.json (we do).
 */
interface TauriInvoker {
    core?: { invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> };
    invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
}

function tauriInvoke(): TauriInvoker["core"] | null {
    const t = (window as unknown as { __TAURI__?: TauriInvoker }).__TAURI__;
    if (!t) return null;
    if (t.core?.invoke) return t.core;
    if (t.invoke) return { invoke: t.invoke };
    return null;
}

export async function isAutostartEnabled(): Promise<boolean> {
    const core = tauriInvoke();
    if (!core) return false;
    try {
        return Boolean(await core.invoke("plugin:autostart|is_enabled"));
    } catch {
        return false;
    }
}

export async function setAutostartEnabled(enabled: boolean): Promise<boolean> {
    const core = tauriInvoke();
    if (!core) return false;
    try {
        await core.invoke(enabled ? "plugin:autostart|enable" : "plugin:autostart|disable");
        return await isAutostartEnabled();
    } catch {
        return false;
    }
}

/**
 * Request push permission + register the device with APN/FCM, then POST the
 * resulting token to our backend so it can address this device when an
 * invite opens. Safe to call multiple times — APN/FCM dedupe on their end,
 * and our backend does INSERT OR UPDATE.
 *
 * Returns the platform-issued token on success, or null if the user denied
 * permission or we're not in a Capacitor shell.
 */
export async function requestAndRegisterPush(
    postToken: (token: string, platform: "ios" | "android") => Promise<void>
): Promise<string | null> {
    const cap = getCapacitor();
    const push = cap?.Plugins?.PushNotifications;
    if (!push || !cap?.getPlatform) return null;
    const platform = cap.getPlatform();
    if (platform !== "ios" && platform !== "android") return null;

    try {
        const perm = await push.requestPermissions();
        if (perm.receive !== "granted") return null;

        return await new Promise<string | null>(async (resolve) => {
            // `registration` event fires with the platform token once APNS/FCM
            // hands it back. Failure path lands in registrationError.
            let resolved = false;
            const regListener = await push.addListener("registration", (payload) => {
                if (resolved) return;
                resolved = true;
                const token = (payload as { value?: string })?.value || "";
                if (!token) {
                    regListener.remove?.();
                    resolve(null);
                    return;
                }
                void postToken(token, platform).catch(() => { /* server down? user retries later */ });
                regListener.remove?.();
                resolve(token);
            });
            await push.addListener("registrationError", () => {
                if (resolved) return;
                resolved = true;
                regListener.remove?.();
                resolve(null);
            });
            await push.register();

            // 15s ceiling — if APNS/FCM hasn't answered by then, something's
            // wrong (network dead, entitlement missing). Don't leave the UI
            // hanging forever.
            setTimeout(() => {
                if (!resolved) {
                    resolved = true;
                    regListener.remove?.();
                    resolve(null);
                }
            }, 15_000);
        });
    } catch {
        return null;
    }
}

/**
 * Wire the Android hardware-back button to the router.
 *
 * Without this, hitting "back" on Android always closes the app — iOS has no
 * hardware back so it's a no-op there. When the router can go back we navigate
 * back; when we're at the root route and the user presses back twice in a row
 * within 2s, we exit (matches the standard Android app convention).
 */
export function wireHardwareBack(router: Router): void {
    const cap = getCapacitor();
    const app = cap?.Plugins?.App;
    if (!app) return;

    let lastPressAt = 0;
    app.addListener("backButton", ({ canGoBack }) => {
        const now = Date.now();
        // History stack has something — pop it.
        if (canGoBack && window.history.length > 1) {
            router.back();
            return;
        }
        // Root route: "press back again to exit" within 2s.
        if (now - lastPressAt < 2000) {
            app.exitApp().catch(() => { /* ignore */ });
            return;
        }
        lastPressAt = now;
        // Surface a toast so the user knows what's going on. Dynamic import so
        // this file doesn't pull toast into the router chunk.
        import("./toast").then(({ showToast }) => {
            showToast("再按一次返回键退出", "info", 1800);
        });
    });
}

/**
 * Keep the native status bar aligned with the current theme (dark/light).
 *
 * `setStyle` controls icon color (so they stay legible over our glass header);
 * `setOverlaysWebView(true)` is what lets the header's `pt-safe` padding
 * actually display the status bar as part of our UI rather than stealing a
 * chunk of vertical real estate.
 */
export function syncStatusBar(isDark: boolean): void {
    const cap = getCapacitor();
    const sb = cap?.Plugins?.StatusBar;
    if (!sb) return;
    sb.setOverlaysWebView({ overlay: true }).catch(() => { });
    sb.setStyle({ style: isDark ? "LIGHT" : "DARK" }).catch(() => { });
}
