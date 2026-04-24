import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Capacitor shell config for PT Invite Watcher mobile.
 *
 * The webDir points at the SAME Vite build output the backend serves as its
 * `/` route — one `npm run build` inside `webui/` produces assets consumed by
 * both the browser deployment and this mobile wrapper.
 *
 * Mobile is always in "remote mode" (see runtime_config.ts) because:
 * - iOS / Android sandboxes cannot spawn the Python sidecar binary.
 * - Long-running background scans are platform-restricted on mobile anyway.
 *
 * The Onboarding page takes the user through entering a server URL + BasicAuth
 * on first launch; credentials go into Capacitor Preferences (which maps to
 * Keychain on iOS / EncryptedSharedPreferences on Android).
 */
const config: CapacitorConfig = {
    appId: "com.pt_invite_watcher.app",
    appName: "PT Invite Watcher",
    // Relative to this config file's directory. Capacitor copies the contents
    // of this folder into the native app bundle at sync time.
    webDir: "../pt_invite_watcher/webui_dist",
    server: {
        // Both iOS and Android default to `https://` as the origin scheme for
        // Capacitor-served content, which makes `fetch("/api/...")` resolve to
        // `https://localhost/api/...` from the WebView. Onboarding rewrites
        // apiBase to the user's remote URL, so the `https://localhost` only
        // matters before the first fetch.
        androidScheme: "https",
        iosScheme: "https",
    },
    android: {
        // A native loading indicator while the bundled HTML parses — avoids
        // the flash-of-blank-screen that confuses first-time users.
        useLegacyBridge: false,
    },
};

export default config;
