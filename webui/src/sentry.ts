/**
 * Lazy-loaded Sentry browser SDK. Only dynamically imports `@sentry/browser`
 * when a DSN actually comes back from `/api/config`; otherwise zero cost to
 * users who don't opt in (no bundle bloat, no requests, no breadcrumbs).
 *
 * Same scrubbing policy as the Python side: drop `token=` query params,
 * `Authorization` headers, and `/api/sites/icon` noise before send.
 */

let initialized = false;

function scrubUrl(url: string): string {
    return url.replace(/token=[^&#]*/g, "token=REDACTED");
}

export async function maybeInitSentry(dsn: string | undefined | null): Promise<void> {
    if (initialized || !dsn) return;
    try {
        const Sentry = await import("@sentry/browser");
        Sentry.init({
            dsn,
            tracesSampleRate: 0,
            sendDefaultPii: false,
            beforeSend: (event) => {
                try {
                    const req = event.request || {};
                    if (req.url) {
                        if (req.url.includes("/api/sites/icon")) return null;
                        req.url = scrubUrl(req.url);
                    }
                    if (typeof req.query_string === "string" && req.query_string.includes("token=")) {
                        req.query_string = req.query_string.replace(/token=[^&#]*/g, "token=REDACTED");
                    }
                    if (req.headers && typeof req.headers === "object") {
                        const headers = req.headers as Record<string, string>;
                        for (const k of Object.keys(headers)) {
                            if (k.toLowerCase() === "authorization") headers[k] = "REDACTED";
                        }
                    }
                    event.request = req;
                } catch {
                    /* scrub bug shouldn't block send */
                }
                return event;
            },
            release: document.documentElement.dataset.appVersion || undefined,
        });
        initialized = true;
    } catch (e) {
        // Runtime import failure (offline install, CDN hiccup for lazy chunk,
        // etc.) — swallow. Observability is best-effort.
        console.warn("sentry init skipped:", e);
    }
}
