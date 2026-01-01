import { ref, onUnmounted } from "vue";

export type SSEEventType = "connected" | "ping" | "dashboard_update" | "logs_update";

export interface SSEMessage {
    type: SSEEventType;
    data?: any;
}

const listeners: Map<SSEEventType, Set<() => void>> = new Map();
let eventSource: EventSource | null = null;
let reconnectTimer: number | undefined;

function connect() {
    if (eventSource) return;

    eventSource = new EventSource("/api/events");

    eventSource.onmessage = (event) => {
        try {
            const msg: SSEMessage = JSON.parse(event.data);
            const callbacks = listeners.get(msg.type);
            if (callbacks) {
                callbacks.forEach((cb) => cb());
            }
        } catch (e) {
            console.warn("SSE parse error:", e);
        }
    };

    eventSource.onerror = () => {
        eventSource?.close();
        eventSource = null;
        // Reconnect after 3 seconds
        reconnectTimer = window.setTimeout(connect, 3000);
    };
}

function disconnect() {
    if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = undefined;
    }
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
}

export function onSSE(eventType: SSEEventType, callback: () => void) {
    if (!listeners.has(eventType)) {
        listeners.set(eventType, new Set());
    }
    listeners.get(eventType)!.add(callback);

    // Start connection if first listener
    if (!eventSource) {
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

// Vue composable for SSE
export function useSSE(eventType: SSEEventType, callback: () => void) {
    const cleanup = onSSE(eventType, callback);
    onUnmounted(cleanup);
}
