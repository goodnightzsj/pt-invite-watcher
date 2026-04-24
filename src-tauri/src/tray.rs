//! System tray icon + menu + close-to-tray behavior.
//!
//! What it does:
//!
//! 1. Puts a tray icon in the OS menu bar (macOS) / system tray (Windows,
//!    Linux) with a menu: Show / Hide / Quit.
//! 2. Hijacks the main window's close (X) button so it hides the window
//!    instead of tearing the process down — sidecar + WebSocket stay alive,
//!    scan loop keeps ticking. User clicks tray → Show to bring it back.
//!    Explicit "Quit" in the tray menu is the only true exit path.
//! 3. Left-click on the tray icon toggles visibility (Windows convention),
//!    matching what users expect from background-monitor style apps.

use tauri::{
    menu::{Menu, MenuEvent, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, WindowEvent,
};

pub fn install_tray(app: &AppHandle) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
    let hide = MenuItem::with_id(app, "hide", "隐藏窗口", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &hide, &quit])?;

    TrayIconBuilder::with_id("main-tray")
        .tooltip("PT Invite Watcher")
        .icon(app.default_window_icon().cloned().unwrap())
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(handle_menu_event)
        .on_tray_icon_event(handle_tray_icon_event)
        .build(app)?;

    Ok(())
}

/// Intercept the close button: hide instead of quit, keeping the sidecar
/// alive in the background. Tauri's `WindowEvent::CloseRequested` fires
/// before the process starts tearing down; we `api.prevent_close()` and
/// hide the window. The only path to true exit is the tray Quit menu item
/// (which calls `app.exit(0)`).
pub fn intercept_close_to_hide(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let handle = app.clone();
        win.on_window_event(move |event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                if let Some(w) = handle.get_webview_window("main") {
                    let _ = w.hide();
                }
            }
        });
    }
}

fn handle_menu_event(app: &AppHandle, event: MenuEvent) {
    match event.id.as_ref() {
        "show" => {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
                let _ = w.set_focus();
            }
        }
        "hide" => {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.hide();
            }
        }
        "quit" => {
            app.exit(0);
        }
        _ => {}
    }
}

fn handle_tray_icon_event(tray: &tauri::tray::TrayIcon, event: TrayIconEvent) {
    // Left-click toggles window visibility — matches the Windows / macOS
    // convention for background-monitor apps. Right-click is owned by
    // Tauri for the menu.
    if let TrayIconEvent::Click {
        button: MouseButton::Left,
        button_state: MouseButtonState::Up,
        ..
    } = event
    {
        let app = tray.app_handle();
        if let Some(w) = app.get_webview_window("main") {
            let visible = w.is_visible().unwrap_or(false);
            let _ = if visible {
                w.hide()
            } else {
                let _ = w.show();
                w.set_focus()
            };
        }
    }
}
