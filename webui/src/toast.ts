import { reactive } from "vue";

export type ToastKind = "success" | "info" | "error";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  count: number;
  timerId: number;
}

let nextId = 0;
const MAX_TOASTS = 5;
// A toast with the same (kind, message) within this window gets merged into a counter.
const DEDUP_WINDOW_MS = 3000;

export const toasts = reactive<ToastItem[]>([]);

function scheduleRemoval(id: number, timeoutMs: number): number {
  return window.setTimeout(() => {
    const idx = toasts.findIndex((t) => t.id === id);
    if (idx >= 0) toasts.splice(idx, 1);
  }, timeoutMs);
}

export function showToast(message: string, kind: ToastKind = "info", timeoutMs = 2400) {
  // Merge if the most recent toast within the dedup window has the same kind+message.
  for (let i = toasts.length - 1; i >= 0; i--) {
    const t = toasts[i];
    if (t.kind === kind && t.message === message) {
      t.count += 1;
      window.clearTimeout(t.timerId);
      t.timerId = scheduleRemoval(t.id, Math.max(timeoutMs, DEDUP_WINDOW_MS));
      return;
    }
  }

  const id = nextId++;
  const timerId = scheduleRemoval(id, timeoutMs);
  toasts.push({ id, kind, message, count: 1, timerId });

  if (toasts.length > MAX_TOASTS) {
    const removed = toasts.shift();
    if (removed) window.clearTimeout(removed.timerId);
  }
}

export function removeToast(id: number) {
  const idx = toasts.findIndex((t) => t.id === id);
  if (idx >= 0) {
    const removed = toasts[idx];
    window.clearTimeout(removed.timerId);
    toasts.splice(idx, 1);
  }
}

// Legacy single toast compat (for existing imports)
export const toast = reactive({
  open: false,
  kind: "info" as ToastKind,
  message: "",
});


