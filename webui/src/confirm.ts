import { reactive } from "vue";

export interface ConfirmState {
    isOpen: boolean;
    title: string;
    message: string;
    resolve: ((value: boolean) => void) | null;
}

export const confirmState = reactive<ConfirmState>({
    isOpen: false,
    title: "",
    message: "",
    resolve: null,
});

export function confirm(message: string, title = "确认操作"): Promise<boolean> {
    return new Promise((resolve) => {
        confirmState.message = message;
        confirmState.title = title;
        confirmState.isOpen = true;
        confirmState.resolve = resolve;
    });
}

export function closeConfirm(result: boolean) {
    if (confirmState.resolve) {
        confirmState.resolve(result);
        confirmState.resolve = null;
    }
    confirmState.isOpen = false;
}
