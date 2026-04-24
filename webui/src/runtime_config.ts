import { reactive } from "vue";

/**
 * Runtime configuration for the API / WebSocket base URLs and auth.
 *
 * ## Why this exists
 *
 * The same compiled webui bundle ships in three contexts:
 *
 * 1. **Browser, same-origin** — the FastAPI backend serves `webui_dist` and
 *    the bundle talks to `/api/...` via relative paths. apiBase stays empty.
 * 2. **Tauri desktop shell, embedded mode** — the app spawns a bundled Python
 *    sidecar on a random local port. The Rust shell writes the port into
 *    `window.__PTIW_RUNTIME__` before the bundle boots; we consume it here.
 * 3. **Tauri desktop or mobile shell, remote mode** — the app is a thin client
 *    connecting to a user-provided FastAPI URL. User completes an Onboarding
 *    flow on first launch; the URL + BasicAuth ride in localStorage (URL) +
 *    platform keychain (credentials, via Tauri plugin).
 *
 * This module hides those three cases behind one small API:
 *
 *     import { apiUrl, wsUrl, authHeader, runtimeConfig } from "./runtime_config";
 *     fetch(apiUrl("/api/dashboard"), { headers: { ...authHeader() } });
 *
 * Existing browser-only deployments see no behavior change — the defaults
 * keep same-origin relative paths intact.
 */

export type RuntimeMode = "embedded" | "remote";

const STORAGE_API_BASE = "ptiw_api_base";
const STORAGE_WS_BASE = "ptiw_ws_base";
const STORAGE_MODE = "ptiw_runtime_mode";
const STORAGE_BASIC_AUTH = "ptiw_basic_auth"; // base64 user:pass — only used in remote browser mode;
                                              // Tauri shells keep this in OS keychain instead.

interface TauriBootstrap {
    apiBase?: string;
    wsBase?: string;
    mode?: RuntimeMode;
    basicAuth?: string; // already base64-encoded by the Rust side
}

function safeGet(key: string): string {
    try {
        return localStorage.getItem(key) || "";
    } catch {
        return "";
    }
}

function safeSet(key: string, val: string): void {
    try {
        if (val) localStorage.setItem(key, val);
        else localStorage.removeItem(key);
    } catch {
        /* private mode — ignore */
    }
}

/**
 * Reactive snapshot. `apiBase === ""` means "use same-origin relative paths",
 * which is the safe default for any unconfigured deployment.
 */
export const runtimeConfig = reactive({
    apiBase: "",
    wsBase: "",
    mode: "remote" as RuntimeMode,
    basicAuth: "",
    // True once `loadRuntimeConfig()` has seeded from storage / Tauri bridge.
    // Used by the root component to decide whether to show Onboarding.
    ready: false,
});

/**
 * Seed the runtime config from all available sources in priority order:
 *
 *   1. A `window.__PTIW_RUNTIME__` object injected by the Tauri Rust shell
 *      (both embedded-mode sidecar and remote-mode bootstrapping use this).
 *   2. `localStorage` values persisted from a prior Onboarding flow.
 *   3. Fallback: empty apiBase (same-origin browser deployment).
 */
export function loadRuntimeConfig(): void {
    const bootstrap = (window as any).__PTIW_RUNTIME__ as TauriBootstrap | undefined;
    if (bootstrap && typeof bootstrap === "object") {
        runtimeConfig.apiBase = bootstrap.apiBase || "";
        runtimeConfig.wsBase = bootstrap.wsBase || "";
        runtimeConfig.mode = bootstrap.mode || "embedded";
        runtimeConfig.basicAuth = bootstrap.basicAuth || "";
        runtimeConfig.ready = true;
        return;
    }

    const storedApi = safeGet(STORAGE_API_BASE);
    const storedWs = safeGet(STORAGE_WS_BASE);
    const storedMode = safeGet(STORAGE_MODE) as RuntimeMode | "";
    const storedAuth = safeGet(STORAGE_BASIC_AUTH);

    runtimeConfig.apiBase = storedApi;
    runtimeConfig.wsBase = storedWs;
    runtimeConfig.mode = storedMode === "embedded" ? "embedded" : "remote";
    runtimeConfig.basicAuth = storedAuth;
    runtimeConfig.ready = true;
}

/**
 * Persist the user's Onboarding choice. Called by OnboardingPage after the
 * user successfully connects to a remote FastAPI instance.
 */
export function saveRemoteConfig(apiBase: string, basicAuth: string): void {
    const trimmed = (apiBase || "").replace(/\/$/, "");
    runtimeConfig.apiBase = trimmed;
    runtimeConfig.wsBase = deriveWsBase(trimmed);
    runtimeConfig.mode = "remote";
    runtimeConfig.basicAuth = basicAuth;
    safeSet(STORAGE_API_BASE, trimmed);
    safeSet(STORAGE_WS_BASE, runtimeConfig.wsBase);
    safeSet(STORAGE_MODE, "remote");
    safeSet(STORAGE_BASIC_AUTH, basicAuth);
}

/**
 * Clear all persisted runtime config. Used by "sign out" from Onboarding in
 * remote mode — lets the user reconfigure from scratch on next launch.
 */
export function resetRuntimeConfig(): void {
    runtimeConfig.apiBase = "";
    runtimeConfig.wsBase = "";
    runtimeConfig.basicAuth = "";
    safeSet(STORAGE_API_BASE, "");
    safeSet(STORAGE_WS_BASE, "");
    safeSet(STORAGE_MODE, "");
    safeSet(STORAGE_BASIC_AUTH, "");
}

/**
 * Derive an appropriate WebSocket origin from an HTTP(S) apiBase. `https://` →
 * `wss://`, `http://` → `ws://`, preserving host + port. If apiBase is empty
 * (same-origin browser) we defer to callers' window.location logic.
 */
export function deriveWsBase(apiBase: string): string {
    if (!apiBase) return "";
    try {
        const u = new URL(apiBase);
        u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
        // Strip any path so wsUrl("/ws/events") appends cleanly.
        u.pathname = "";
        return u.toString().replace(/\/$/, "");
    } catch {
        return "";
    }
}

/** Prepend apiBase to a relative API path. Empty apiBase → same-origin. */
export function apiUrl(path: string): string {
    const base = runtimeConfig.apiBase;
    if (!base) return path;
    return base + (path.startsWith("/") ? path : `/${path}`);
}

/**
 * Build a fully-qualified WebSocket URL. Priority:
 *   1. runtimeConfig.wsBase (set by Tauri shell or Onboarding)
 *   2. Derived from apiBase
 *   3. Derived from window.location (same-origin browser)
 *
 * When BasicAuth credentials are configured (Tauri sidecar token / remote-mode
 * Onboarding entry), we append `?token=<base64 user:pass>` — browsers can't
 * set custom headers on `new WebSocket(url)` so query-param is the standard
 * way to pass credentials through a WS handshake. Same-origin browser
 * deployments still ride the HTTP BasicAuth challenge that the browser
 * remembers, so no token is needed there.
 */
export function wsUrl(path: string): string {
    const wsBase = runtimeConfig.wsBase || deriveWsBase(runtimeConfig.apiBase);
    let baseUrl = "";
    if (wsBase) {
        baseUrl = wsBase + (path.startsWith("/") ? path : `/${path}`);
    } else {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        baseUrl = `${proto}//${window.location.host}${path}`;
    }
    if (runtimeConfig.basicAuth) {
        const sep = baseUrl.includes("?") ? "&" : "?";
        return `${baseUrl}${sep}token=${encodeURIComponent(runtimeConfig.basicAuth)}`;
    }
    return baseUrl;
}

/**
 * Auth header dict for cross-origin requests. Empty when running same-origin
 * (the browser's own cookie / BasicAuth challenge handles it) or when no
 * credentials have been provided.
 */
export function authHeader(): Record<string, string> {
    if (!runtimeConfig.basicAuth) return {};
    return { Authorization: `Basic ${runtimeConfig.basicAuth}` };
}

/** True when the current runtime needs the user to complete Onboarding. */
export function needsOnboarding(): boolean {
    // Tauri bootstrap fills apiBase, so ready + empty apiBase + running inside
    // a Tauri shell = remote mode waiting for user to configure.
    if (!runtimeConfig.ready) return false;
    const isTauri = typeof (window as any).__TAURI_INTERNALS__ !== "undefined" || typeof (window as any).__TAURI__ !== "undefined";
    return isTauri && runtimeConfig.mode === "remote" && !runtimeConfig.apiBase;
}
