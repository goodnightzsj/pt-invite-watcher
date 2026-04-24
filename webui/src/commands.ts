import { reactive } from "vue";

/**
 * Central registry of keyboard-discoverable actions for the command palette.
 *
 * Keeping commands in a central store (rather than component-local)
 * means the palette can execute them without importing every page —
 * each page registers its context-specific commands at mount time and
 * unregisters on unmount, while global ones (navigate-to-X, theme
 * toggle, scan trigger via emit) live here permanently.
 */
export type CommandCategory = "导航" | "操作" | "设置" | "最近";

export interface CommandDef {
    id: string;
    label: string;
    category: CommandCategory;
    aliases?: string[];
    shortcut?: string;
    keywords?: string;
    run: () => void | Promise<void>;
}

const _commands = reactive<Map<string, CommandDef>>(new Map());
const _recentIds = reactive<string[]>([]);
const RECENT_MAX = 5;
const RECENT_STORAGE = "ptiw_cmd_recent";

function loadRecent(): string[] {
    try {
        const raw = localStorage.getItem(RECENT_STORAGE);
        if (!raw) return [];
        const arr = JSON.parse(raw);
        return Array.isArray(arr) ? arr.filter((x) => typeof x === "string") : [];
    } catch {
        return [];
    }
}
function saveRecent(): void {
    try {
        localStorage.setItem(RECENT_STORAGE, JSON.stringify(_recentIds.slice(0, RECENT_MAX)));
    } catch { /* private mode */ }
}
_recentIds.push(...loadRecent());

export function registerCommand(cmd: CommandDef): () => void {
    _commands.set(cmd.id, cmd);
    return () => { _commands.delete(cmd.id); };
}

export function registerCommands(cmds: CommandDef[]): () => void {
    const offs = cmds.map(registerCommand);
    return () => { offs.forEach((off) => off()); };
}

export function allCommands(): CommandDef[] {
    return Array.from(_commands.values());
}

export function recentCommandIds(): string[] {
    return [..._recentIds];
}

export async function executeCommand(id: string): Promise<void> {
    const cmd = _commands.get(id);
    if (!cmd) return;
    // Move to front of recent list, de-duplicated, capped.
    const i = _recentIds.indexOf(id);
    if (i !== -1) _recentIds.splice(i, 1);
    _recentIds.unshift(id);
    if (_recentIds.length > RECENT_MAX) _recentIds.splice(RECENT_MAX);
    saveRecent();
    await cmd.run();
}

/**
 * Fuzzy match: each query token must appear in at least one of label /
 * aliases / keywords (case-insensitive substring). Matches all tokens (AND
 * semantics) so "dash sites" doesn't accidentally match "Dashboard" alone.
 */
export function filterCommands(query: string): CommandDef[] {
    const q = query.trim().toLowerCase();
    if (!q) return allCommands();
    const tokens = q.split(/\s+/).filter(Boolean);
    return allCommands().filter((cmd) => {
        const hay = [cmd.label, ...(cmd.aliases || []), cmd.keywords || ""].join(" ").toLowerCase();
        return tokens.every((t) => hay.includes(t));
    });
}
