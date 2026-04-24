/**
 * Backgrounded-tab unread counter, rendered into `document.title`.
 *
 * When the Dashboard detects a new "invites just opened" event while the
 * browser tab is not visible (`document.hidden === true`), it calls
 * `bumpBadge(n)`. The title prepends `(N) ` so the counter shows up in:
 *   - Browser tab strip
 *   - macOS dock badge (via the Page Visibility + favicon combination some
 *     browsers expose)
 *   - Capacitor Android/iOS app-switcher preview's URL hint
 *
 * The badge clears when the tab becomes visible again — the user has seen
 * the new state first-hand.
 *
 * Counter lives as a module-level `let` rather than a store/pinia because
 * only one Dashboard mounts at a time and the value is ephemeral.
 */
let unreadCount = 0;
let baseTitle = "";

function captureBaseTitle(): string {
    if (baseTitle) return baseTitle;
    // Strip any previous badge prefix so we don't accumulate layers across
    // route changes. `(N) Foo · Bar` → `Foo · Bar`.
    const m = document.title.match(/^\(\d+\)\s*(.*)$/);
    baseTitle = m ? m[1] : document.title;
    return baseTitle;
}

function render(): void {
    captureBaseTitle();
    const prefix = unreadCount > 0 ? `(${unreadCount}) ` : "";
    document.title = `${prefix}${baseTitle}`;
}

export function bumpBadge(by = 1): void {
    unreadCount += by;
    render();
}

export function clearBadge(): void {
    unreadCount = 0;
    render();
}

/** Observe page-visibility and clear the badge when the user returns. */
export function installBadgeResetOnVisible(): void {
    if (typeof document === "undefined") return;
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) clearBadge();
    });
}

/**
 * Called by the router's `afterEach` to re-capture the baseline after a route
 * change has rewritten `document.title`. Without this the badge prefix would
 * wrap around the stale previous title.
 */
export function rebaseTitleAfterRouteChange(): void {
    baseTitle = "";
    render();
}
