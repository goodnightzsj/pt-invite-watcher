import { reactive } from "vue";

type ToastKind = "success" | "info" | "error";

export const toast = reactive({
  open: false,
  kind: "info" as ToastKind,
  message: "",
});

let timer: number | undefined;

export function showToast(message: string, kind: ToastKind = "info", timeoutMs = 2400) {
  toast.open = true;
  toast.kind = kind;
  toast.message = message;
  if (timer) window.clearTimeout(timer);
  timer = window.setTimeout(() => {
    toast.open = false;
  }, timeoutMs);
}

