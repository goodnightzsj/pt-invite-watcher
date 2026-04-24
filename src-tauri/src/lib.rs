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

use std::net::TcpListener;

use serde_json::json;
use tauri::Manager;

mod sidecar;

// The `#[tauri::mobile_entry_point]` attribute is how the Android / iOS
// targets know where to hand off control after JNI / Swift boot. Desktop
// targets ignore it (compiled via `main.rs` → `run()` directly).
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::try_init().ok();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // Mobile targets cannot spawn arbitrary subprocesses; force remote mode.
            #[cfg(any(target_os = "android", target_os = "ios"))]
            let embedded_result: Result<Option<sidecar::Sidecar>, String> = Ok(None);

            #[cfg(not(any(target_os = "android", target_os = "ios")))]
            let embedded_result = sidecar::try_start_embedded(app.handle());

            let main_window = app
                .get_webview_window("main")
                .ok_or("main window missing")?;

            let bootstrap = match embedded_result {
                Ok(Some(sc)) => {
                    let api_base = format!("http://127.0.0.1:{}", sc.port);
                    let ws_base = format!("ws://127.0.0.1:{}", sc.port);
                    // Store the sidecar on app state so it's dropped cleanly on exit.
                    app.manage(sc);
                    json!({
                        "apiBase": api_base,
                        "wsBase": ws_base,
                        "mode": "embedded",
                    })
                }
                Ok(None) => json!({ "mode": "remote" }),
                Err(err) => {
                    log::warn!("embedded sidecar failed to start: {err}; falling back to remote mode");
                    json!({
                        "mode": "remote",
                        "sidecarError": err,
                    })
                }
            };

            // Inject __PTIW_RUNTIME__ before the webview's JS runs. Tauri 2 queues
            // initialization scripts to fire before the first page load.
            let script = format!(
                "window.__PTIW_RUNTIME__ = {};",
                serde_json::to_string(&bootstrap).unwrap_or_else(|_| "{{}}".into())
            );
            main_window.eval(&script).ok();

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}

/// Grab any free localhost port without holding it — the sidecar process will
/// re-bind the same number milliseconds later. Small race window in practice;
/// re-attempt on failure in the sidecar module.
#[allow(dead_code)]
fn pick_port() -> Option<u16> {
    let listener = TcpListener::bind("127.0.0.1:0").ok()?;
    let port = listener.local_addr().ok()?.port();
    drop(listener);
    Some(port)
}
