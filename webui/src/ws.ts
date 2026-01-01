import { onUnmounted } from "vue";

export type WSEventType = "connected" | "ping" | "dashboard_update" | "logs_update" | "logs_append";

export interface WSMessage {
    type: WSEventType;
    data?: any;
}

const listeners: Map<WSEventType, Set<(data?: any) => void>> = new Map();
let socket: WebSocket | null = null;
let reconnectTimer: number | undefined;
let pingTimer: number | undefined;

function connect() {
    if (socket) return;

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${proto}//${host}/ws/events`;

    socket = new WebSocket(url);

    socket.onopen = () => {
        // console.log("WS connected");
        startPing();
        if (reconnectTimer) {
            window.clearTimeout(reconnectTimer);
            reconnectTimer = undefined;
        }
    };

    socket.onmessage = (event) => {
        try {
            const msg: WSMessage = JSON.parse(event.data);
            if (msg.type === "ping") return; // Ignore pong/ping echo if any

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
        // Reconnect after 3 seconds
        reconnectTimer = window.setTimeout(connect, 3000);
    };

    socket.onerror = (e) => {
        console.warn("WS error:", e);
        // onclose will be called
    };
}

function startPing() {
    stopPing();
    pingTimer = window.setInterval(() => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send("ping");
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
        socket.close();
        socket = null;
    }
}

function disconnect() {
    if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = undefined;
    }
    cleanupSocket();
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
