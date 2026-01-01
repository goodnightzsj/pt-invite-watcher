import { reactive } from "vue";

export type ToastKind = "success" | "info" | "error";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

let nextId = 0;
const MAX_TOASTS = 5;

export const toasts = reactive<ToastItem[]>([]);

export function showToast(message: string, kind: ToastKind = "info", timeoutMs = 2400) {
  const id = nextId++;
  const item: ToastItem = { id, kind, message };

  // Add to queue (newest at end)
  toasts.push(item);

  // Limit max toasts
  if (toasts.length > MAX_TOASTS) {
    toasts.shift();
  }

  // Auto remove after timeout
  window.setTimeout(() => {
    const idx = toasts.findIndex((t) => t.id === id);
    if (idx >= 0) toasts.splice(idx, 1);
  }, timeoutMs);
}

export function removeToast(id: number) {
  const idx = toasts.findIndex((t) => t.id === id);
  if (idx >= 0) toasts.splice(idx, 1);
}

// Legacy single toast compat (for existing imports)
export const toast = reactive({
  open: false,
  kind: "info" as ToastKind,
  message: "",
});


