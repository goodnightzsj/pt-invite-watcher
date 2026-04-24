//! Tauri 2 shell for PT Invite Watcher.
//!
//! Responsibilities:
//!
//! 1. **Embedded mode (desktop only)** — spawn the bundled Python sidecar
//!    (`pt-invite-watcher-server`) on a random free localhost port, wait for
//!    its `/health` endpoint to answer, then inject the resolved URL into the
//!    webview as `window.__PTIW_RUNTIME__` before the Vue app boots.
//!
//! 2. **Remote mode (mobile default; desktop fallback)** — skip the sidecar
//!    and let the webview's Onboarding flow prompt the user for a server URL.
//!    We still inject a bootstrap object so the Vue layer knows to switch to
//!    remote mode instead of guessing from `window.location`.
//!
//! 3. **Clean shutdown** — kill the sidecar (if any) when the main window
//!    closes. No orphan Python processes after `Cmd+Q`.

use serde_json::json;
use tauri::Manager;

// Sidecar is only relevant on desktop — iOS / Android cannot spawn Python
// subprocesses (platform sandbox). Cfg-gate the whole module so mobile builds
// don't drag in `reqwest::blocking` or try to resolve the sidecar binary.
#[cfg(not(any(target_os = "android", target_os = "ios")))]
mod sidecar;

// Tray UI and close-to-tray behavior are desktop-only — mobile shells don't
// have a system tray concept.
#[cfg(not(any(target_os = "android", target_os = "ios")))]
mod tray;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        // Desktop autostart — users toggle from Config → 界面设置. Registering
        // the plugin with `None` args means the CLI command used to re-launch
        // the app is the default (the executable path). No-op on mobile.
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .setup(|app| {
            let main_window = app
                .get_webview_window("main")
                .ok_or("main window missing")?;

            // Mobile targets can't spawn the Python sidecar (sandbox forbids
            // arbitrary subprocesses) — they boot straight into remote mode,
            // so keep the sidecar code path off their compilation path entirely.
            #[cfg(not(any(target_os = "android", target_os = "ios")))]
            let bootstrap = match sidecar::try_start_embedded(app.handle()) {
                Ok(Some(sc)) => {
                    let api_base = format!("http://127.0.0.1:{}", sc.port);
                    let ws_base = format!("ws://127.0.0.1:{}", sc.port);
                    let basic_auth = sc.basic_auth.clone();
                    // Store the sidecar on app state so it's dropped cleanly on exit.
                    app.manage(sc);
                    json!({
                        "apiBase": api_base,
                        "wsBase": ws_base,
                        "mode": "embedded",
                        // Random per-launch BasicAuth so another local process
                        // on the same machine can't read the sidecar's data
                        // even though the port is guessable.
                        "basicAuth": basic_auth,
                    })
                }
                Ok(None) => json!({ "mode": "remote" }),
                Err(err) => {
                    eprintln!("embedded sidecar failed to start: {err}; falling back to remote mode");
                    json!({
                        "mode": "remote",
                        "sidecarError": err,
                    })
                }
            };

            #[cfg(any(target_os = "android", target_os = "ios"))]
            let bootstrap = json!({ "mode": "remote" });

            // Inject __PTIW_RUNTIME__ before the webview's JS runs. Tauri 2 queues
            // initialization scripts to fire before the first page load.
            let script = format!(
                "window.__PTIW_RUNTIME__ = {};",
                serde_json::to_string(&bootstrap).unwrap_or_else(|_| "{{}}".into())
            );
            main_window.eval(&script).ok();

            // Desktop-only: system tray + close-to-hide. Mobile doesn't have
            // a tray concept and its close-button semantics are handled by
            // the OS (swipe away from app switcher).
            #[cfg(not(any(target_os = "android", target_os = "ios")))]
            {
                if let Err(e) = tray::install_tray(app.handle()) {
                    eprintln!("tray install failed: {e}; continuing without tray");
                }
                tray::intercept_close_to_hide(app.handle());
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}

