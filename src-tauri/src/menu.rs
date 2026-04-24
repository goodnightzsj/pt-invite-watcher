//! Native macOS menu bar.
//!
//! macOS users expect a standard menu bar layout: App menu with About/Hide/Quit,
//! Edit with Undo/Redo/Cut/Copy/Paste/Select All, View with Reload/Toggle DevTools,
//! Window with Minimize/Close. Without it the app feels foreign (Cmd+Q works
//! but Cmd+C in an input falls back to Tauri's webview default, which on some
//! versions is buggy).
//!
//! Cfg-gated to macOS only. Windows has its own in-window menu pattern and Linux
//! distros vary too much to bake a default; both are fine with our existing
//! browser-like keyboard shortcuts (Cmd+R to scan wired in main.ts).

#[cfg(target_os = "macos")]
use tauri::{
    menu::{AboutMetadataBuilder, MenuBuilder, MenuItemBuilder, PredefinedMenuItem, SubmenuBuilder},
    AppHandle, Emitter,
};

#[cfg(target_os = "macos")]
pub fn install_menu(app: &AppHandle) -> tauri::Result<()> {
    let about = AboutMetadataBuilder::new()
        .name(Some("PT Invite Watcher"))
        .version(Some(env!("CARGO_PKG_VERSION")))
        .copyright(Some("PT Invite Watcher"))
        .build();

    // App menu (first, always rendered as app name on macOS).
    let app_menu = SubmenuBuilder::new(app, "PT Invite Watcher")
        .item(&PredefinedMenuItem::about(app, None, Some(about))?)
        .separator()
        .item(&PredefinedMenuItem::hide(app, None)?)
        .item(&PredefinedMenuItem::hide_others(app, None)?)
        .item(&PredefinedMenuItem::show_all(app, None)?)
        .separator()
        .item(&PredefinedMenuItem::quit(app, None)?)
        .build()?;

    let edit_menu = SubmenuBuilder::new(app, "Edit")
        .item(&PredefinedMenuItem::undo(app, None)?)
        .item(&PredefinedMenuItem::redo(app, None)?)
        .separator()
        .item(&PredefinedMenuItem::cut(app, None)?)
        .item(&PredefinedMenuItem::copy(app, None)?)
        .item(&PredefinedMenuItem::paste(app, None)?)
        .item(&PredefinedMenuItem::select_all(app, None)?)
        .build()?;

    // View menu: fullscreen + a custom "立即扫描" that emits a JS event
    // the dashboard listens for. Cmd+Shift+R is the convention (Cmd+R alone
    // reloads the webview; we leave that to the browser-style shortcut in
    // main.ts).
    let scan_now = MenuItemBuilder::new("立即扫描")
        .id("menu-scan-now")
        .accelerator("CmdOrCtrl+Shift+R")
        .build(app)?;
    let view_menu = SubmenuBuilder::new(app, "View")
        .item(&scan_now)
        .separator()
        .item(&PredefinedMenuItem::fullscreen(app, None)?)
        .build()?;

    // `bring_all_to_front` isn't in Tauri v2's PredefinedMenuItem API (it's
    // only available on macOS's native NSMenu via AppKit). Stick to what's
    // portable — Minimize + Close are enough for the vast majority of
    // window-menu muscle memory.
    let window_menu = SubmenuBuilder::new(app, "Window")
        .item(&PredefinedMenuItem::minimize(app, None)?)
        .item(&PredefinedMenuItem::close_window(app, None)?)
        .build()?;

    let menu = MenuBuilder::new(app)
        .item(&app_menu)
        .item(&edit_menu)
        .item(&view_menu)
        .item(&window_menu)
        .build()?;

    app.set_menu(menu)?;

    // Wire the custom "立即扫描" item to a webview event the dashboard picks
    // up and turns into an actual scan trigger — keeps the Rust side out
    // of app logic.
    let app_handle = app.clone();
    app.on_menu_event(move |_app, event| {
        if event.id() == "menu-scan-now" {
            let _ = app_handle.emit("menu:scan-now", ());
        }
    });

    Ok(())
}

#[cfg(not(target_os = "macos"))]
pub fn install_menu(_app: &tauri::AppHandle) -> tauri::Result<()> {
    // Windows + Linux keep the default frame menus; no custom menu bar.
    Ok(())
}
