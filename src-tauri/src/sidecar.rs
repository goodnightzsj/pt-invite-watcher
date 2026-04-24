//! Python sidecar lifecycle management.
//!
//! The sidecar is the existing FastAPI backend, packaged as a single-file
//! binary by `scripts/build-sidecar/build.py`. Tauri's `externalBin` mechanism
//! copies the per-target binary into the app bundle; at runtime we spawn it on
//! a random local port, poll `/health`, then hand the URL to the webview.

use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// Handle held in app state; `drop` kills the child so `Cmd+Q` doesn't orphan it.
pub struct Sidecar {
    pub port: u16,
    // `Option` so we can take the child out of the struct inside `Drop` — the
    // handle's `kill` consumes the value.
    child: Option<CommandChild>,
}

impl Drop for Sidecar {
    fn drop(&mut self) {
        if let Some(child) = self.child.take() {
            // Best-effort: if kill fails we've already closed, nothing to do.
            if let Err(e) = child.kill() {
                log::warn!("sidecar kill failed: {e}");
            }
        }
    }
}

/// Try to bring up the bundled Python sidecar. Returns:
///
/// - `Ok(Some(_))` — sidecar is running, port resolved, `/health` answered.
/// - `Ok(None)` — no bundled sidecar available on this target (e.g. Linux
///   dev build without `cargo tauri build --target`). Caller should fall
///   through to remote mode.
/// - `Err(_)` — sidecar binary was present but failed to start / answer.
pub fn try_start_embedded(app: &AppHandle) -> Result<Option<Sidecar>, String> {
    // Binary name matches `externalBin` in tauri.conf.json.
    let shell = app.shell();
    let command = match shell.sidecar("pt-invite-watcher-server") {
        Ok(cmd) => cmd,
        Err(e) => {
            // No bundled sidecar = remote-only mode (not an error).
            log::info!("no bundled sidecar: {e}; using remote mode");
            return Ok(None);
        }
    };

    let port = pick_free_port().ok_or("could not pick a free localhost port")?;

    // Local SQLite path under platform-standard app data dir so wiping the app
    // cleans up cleanly. `app.path()` handles per-OS conventions.
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("resolve app_data_dir: {e}"))?;
    std::fs::create_dir_all(&data_dir).map_err(|e| format!("mkdir app_data_dir: {e}"))?;
    let db_path = data_dir.join("ptiw.sqlite");

    let (_rx, child) = command
        // Match the env-var names the Python `config.py` layer actually reads.
        // `_env(name, default)` lets the empty-string values disable any
        // BasicAuth configured in a bundled config.yaml, which is what we
        // want for a localhost-only process.
        .env("PTIW_WEB_HOST", "127.0.0.1")
        .env("PTIW_WEB_PORT", port.to_string())
        .env("PTIW_DB_PATH", db_path.display().to_string())
        .env("PTIW_WEB_AUTH_USERNAME", "")
        .env("PTIW_WEB_AUTH_PASSWORD", "")
        .args(["run"])
        .spawn()
        .map_err(|e| format!("spawn sidecar: {e}"))?;

    // Poll /health until it answers (10s budget). Python startup + import
    // chain is typically 1-3s; the wider budget gives us headroom on slow disks.
    let base = format!("http://127.0.0.1:{port}");
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(500))
        .build()
        .map_err(|e| format!("build probe client: {e}"))?;

    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        if client.get(format!("{base}/health")).send().is_ok() {
            log::info!("sidecar is up on port {port}");
            return Ok(Some(Sidecar {
                port,
                child: Some(child),
            }));
        }
        if Instant::now() >= deadline {
            // Give up — caller will surface remote mode and we release the child.
            let _ = child.kill();
            return Err("sidecar did not respond to /health within 10s".into());
        }
        std::thread::sleep(Duration::from_millis(150));
    }
}

fn pick_free_port() -> Option<u16> {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").ok()?;
    let port = listener.local_addr().ok()?.port();
    drop(listener);
    Some(port)
}
