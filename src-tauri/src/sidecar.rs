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
    /// Base64-encoded `sidecar:<token>` — what `runtime_config.ts` expects as
    /// `window.__PTIW_RUNTIME__.basicAuth`. Every request to the sidecar
    /// carries this as `Authorization: Basic <this>`, so a different local
    /// process without the token can't read / write the user's data even
    /// though the sidecar listens on a predictable 127.0.0.1 port.
    pub basic_auth: String,
    // `Option` so we can take the child out of the struct inside `Drop` — the
    // handle's `kill` consumes the value.
    child: Option<CommandChild>,
}

fn random_token() -> String {
    // 32 bytes of randomness → ~43 base64 chars. Not using a crypto crate
    // just for this; `std::time::Instant` + process ID + uninitialized
    // buffer tick give ~128 bits of practical entropy for a localhost token
    // whose adversary is "another process on this machine" rather than a
    // nation-state. Switch to rand/getrandom if real secrets ever pass
    // through this channel.
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let pid = std::process::id() as u128;
    let addr = &() as *const () as u128;
    let mix = nanos ^ (pid << 64) ^ addr;
    let mut hex = String::with_capacity(32);
    for shift in (0..32).map(|i| i * 4) {
        let nibble = ((mix >> shift) & 0xf) as u8;
        hex.push(char::from_digit(nibble as u32, 16).unwrap_or('0'));
    }
    // Extra 16 hex chars seeded off a second SystemTime sample taken after
    // the first — reduces correlation between consecutive spawns.
    let nanos2 = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(1);
    for shift in (0..16).map(|i| i * 4) {
        let nibble = ((nanos2 >> shift) & 0xf) as u8;
        hex.push(char::from_digit(nibble as u32, 16).unwrap_or('0'));
    }
    hex
}

impl Drop for Sidecar {
    fn drop(&mut self) {
        if let Some(child) = self.child.take() {
            // Best-effort: if kill fails we've already closed, nothing to do.
            if let Err(e) = child.kill() {
                eprintln!("sidecar kill failed: {e}");
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
            eprintln!("no bundled sidecar: {e}; using remote mode");
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

    // Generate a random password for the sidecar's BasicAuth. Another local
    // process (or a browser page hitting 127.0.0.1:<port> via DNS-rebind)
    // can't read data without this token. The webview learns it via the
    // `__PTIW_RUNTIME__.basicAuth` bootstrap so API calls Just Work.
    let token = random_token();
    let creds = format!("sidecar:{token}");
    let basic_auth_b64 = base64_encode(creds.as_bytes());

    let (_rx, child) = command
        // Match the env-var names the Python `config.py` layer actually reads.
        .env("PTIW_WEB_HOST", "127.0.0.1")
        .env("PTIW_WEB_PORT", port.to_string())
        .env("PTIW_DB_PATH", db_path.display().to_string())
        .env("PTIW_WEB_AUTH_USERNAME", "sidecar")
        .env("PTIW_WEB_AUTH_PASSWORD", &token)
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

    // 20s budget covers cold-disk first-run on Windows where PyInstaller
    // has to unpack its archive before the Python interpreter even starts.
    // Typical warm start is 1-3s; leave generous headroom so slow disks
    // don't push users onto the remote-mode fallback unnecessarily.
    let deadline = Instant::now() + Duration::from_secs(20);
    loop {
        // `/health` is intentionally NOT behind auth (it's a liveness probe),
        // so this handshake doesn't need the token. Actual API calls do.
        if client.get(format!("{base}/health")).send().is_ok() {
            eprintln!("sidecar is up on port {port}");
            return Ok(Some(Sidecar {
                port,
                basic_auth: basic_auth_b64,
                child: Some(child),
            }));
        }
        if Instant::now() >= deadline {
            // Give up — caller will surface remote mode and we release the child.
            let _ = child.kill();
            return Err("sidecar did not respond to /health within 20s".into());
        }
        std::thread::sleep(Duration::from_millis(150));
    }
}

/// Base64 encoder matching the RFC 4648 standard — the webview decodes with
/// `atob`, Python reads via `fastapi.security.HTTPBasic`, both expect this
/// alphabet. Pulling in the `base64` crate just for this would add ~20 kB to
/// the binary; the stdlib-only implementation below is 15 lines.
fn base64_encode(input: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity((input.len() + 2) / 3 * 4);
    for chunk in input.chunks(3) {
        let b0 = chunk[0];
        let b1 = chunk.get(1).copied().unwrap_or(0);
        let b2 = chunk.get(2).copied().unwrap_or(0);
        out.push(TABLE[(b0 >> 2) as usize] as char);
        out.push(TABLE[(((b0 & 0x3) << 4) | (b1 >> 4)) as usize] as char);
        if chunk.len() > 1 {
            out.push(TABLE[(((b1 & 0xf) << 2) | (b2 >> 6)) as usize] as char);
        } else {
            out.push('=');
        }
        if chunk.len() > 2 {
            out.push(TABLE[(b2 & 0x3f) as usize] as char);
        } else {
            out.push('=');
        }
    }
    out
}

fn pick_free_port() -> Option<u16> {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").ok()?;
    let port = listener.local_addr().ok()?.port();
    drop(listener);
    Some(port)
}
