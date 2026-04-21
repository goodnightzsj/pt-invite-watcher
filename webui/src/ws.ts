import { onUnmounted } from "vue";

import { WS_PING } from "./ws_events";
import type { WSEventType } from "./ws_events";
export type { WSEventType } from "./ws_events";

export interface WSMessage {
    type: WSEventType;
    data?: any;
}

const listeners: Map<WSEventType, Set<(data?: any) => void>> = new Map();
let socket: WebSocket | null = null;
let reconnectTimer: number | undefined;
let pingTimer: number | undefined;
let retryCount = 0;

// Exponential backoff: 1s, 2s, 4s, 8s, 16s, capped at 30s.
function nextBackoffMs(): number {
    const base = Math.min(30000, 1000 * Math.pow(2, Math.min(retryCount, 6)));
    // ±25% jitter to avoid thundering herd
    const jitter = base * (Math.random() * 0.5 - 0.25);
    return Math.max(500, Math.round(base + jitter));
}

function scheduleReconnect() {
    if (reconnectTimer) return;
    const delay = nextBackoffMs();
    retryCount++;
    reconnectTimer = window.setTimeout(() => {
        reconnectTimer = undefined;
        // Skip reconnect if the page is hidden — will retry on visibilitychange.
        if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
        if (listeners.size === 0) return;
        connect();
    }, delay);
}

function connect() {
    if (socket) return;

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${proto}//${host}/ws/events`;

    try {
        socket = new WebSocket(url);
    } catch (e) {
        scheduleReconnect();
        return;
    }

    socket.onopen = () => {
        retryCount = 0;
        startPing();
        if (reconnectTimer) {
            window.clearTimeout(reconnectTimer);
            reconnectTimer = undefined;
        }
    };

    socket.onmessage = (event) => {
        lastInboundAt = Date.now();
        try {
            const msg: WSMessage = JSON.parse(event.data);
            if (msg.type === WS_PING) return; // Ignore pong/ping echo if any

            const callbacks = listeners.get(msg.type);
            if (callbacks) {
                callbacks.forEach((cb) => cb(msg.data));
            }
        } catch (e) {
            console.warn("WS parse error:", e);
        }
    };

    socket.onclose = () => {
        cleanupSocket();
        if (listeners.size > 0) scheduleReconnect();
    };

    socket.onerror = (e) => {
        console.warn("WS error:", e);
        // onclose will be called
    };
}

// Track the last time we saw any traffic from the server (a pong message resets it).
// If we go too long without traffic, force a reconnect — covers the case where the
// underlying TCP connection died but neither side noticed (no FIN/RST received).
let lastInboundAt = 0;
const STALE_TIMEOUT_MS = 90_000; // 3× ping interval

function startPing() {
    stopPing();
    lastInboundAt = Date.now();
    pingTimer = window.setInterval(() => {
        if (!socket || socket.readyState !== WebSocket.OPEN) return;
        if (Date.now() - lastInboundAt > STALE_TIMEOUT_MS) {
            // Server hasn't responded to our pings in a while — force a reconnect cycle.
            try { socket.close(); } catch { /* ignore */ }
            return;
        }
        try {
            socket.send("ping");
        } catch (e) {
            // Socket may have transitioned; onclose will handle reconnect.
        }
    }, 30000);
}

function stopPing() {
    if (pingTimer) {
        window.clearInterval(pingTimer);
        pingTimer = undefined;
    }
}

function cleanupSocket() {
    stopPing();
    if (socket) {
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;
        socket.onopen = null;
        try { socket.close(); } catch { /* ignore */ }
        socket = null;
    }
}

function disconnect() {
    if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = undefined;
    }
    retryCount = 0;
    cleanupSocket();
}

// Reconnect eagerly when the tab becomes visible again.
if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState !== "visible") return;
        if (listeners.size === 0) return;
        if (socket && socket.readyState === WebSocket.OPEN) return;
        if (reconnectTimer) {
            window.clearTimeout(reconnectTimer);
            reconnectTimer = undefined;
        }
        retryCount = 0;
        connect();
    });
}

export function onWS(eventType: WSEventType, callback: (data?: any) => void) {
    if (!listeners.has(eventType)) {
        listeners.set(eventType, new Set());
    }
    listeners.get(eventType)!.add(callback);

    // Start connection if first listener
    if (!socket) {
        connect();
    }

    // Return cleanup function
    return () => {
        listeners.get(eventType)?.delete(callback);

        // Disconnect if no more listeners
        let total = 0;
        listeners.forEach((set) => (total += set.size));
        if (total === 0) {
            disconnect();
        }
    };
}

// Vue composable for WebSocket
export function useWS(eventType: WSEventType, callback: (data?: any) => void) {
    const cleanup = onWS(eventType, callback);
    onUnmounted(cleanup);
}
