import { ref } from "vue";

/**
 * Browser-local favicon cache.
 *
 * The cache itself lives in `localStorage[CACHE_KEY]` under `SiteIcon.vue`; this
 * module is just the public control surface so the Config page can clear /
 * size-check the cache without reaching into the component. Components watch
 * `iconCacheVersion` and refetch when it bumps, so "clear cache" takes effect
 * immediately without a page reload.
 */
export const ICON_CACHE_KEY = "ptiw_icon_cache";

// Reactive generation counter. Any <SiteIcon> that `watch`es this will drop
// its in-memory `displaySrc` and re-run the fetch chain when we bump it.
export const iconCacheVersion = ref(0);

export function getIconCacheSize(): number {
    try {
        const raw = localStorage.getItem(ICON_CACHE_KEY);
        if (!raw) return 0;
        const obj = JSON.parse(raw);
        return obj && typeof obj === "object" ? Object.keys(obj).length : 0;
    } catch {
        return 0;
    }
}

export function clearIconCache(): void {
    try {
        localStorage.removeItem(ICON_CACHE_KEY);
    } catch {
        /* private mode / disabled storage — ignore */
    }
    iconCacheVersion.value += 1;
}

/**
 * Lazy sweeper: walk the persisted cache and drop entries whose `fetchedAt`
 * is older than `maxAgeMs`. Called on first mount of SiteIcon so the cache
 * doesn't grow forever with orphaned entries from deleted sites.
 */
export function sweepExpiredEntries(maxAgeMs: number): number {
    try {
        const raw = localStorage.getItem(ICON_CACHE_KEY);
        if (!raw) return 0;
        const obj = JSON.parse(raw);
        if (!obj || typeof obj !== "object") return 0;
        const now = Date.now();
        let removed = 0;
        for (const key of Object.keys(obj)) {
            const entry = obj[key];
            if (entry && typeof entry === "object" && typeof entry.fetchedAt === "number") {
                if (now - entry.fetchedAt > maxAgeMs) {
                    delete obj[key];
                    removed += 1;
                }
            }
        }
        if (removed > 0) {
            localStorage.setItem(ICON_CACHE_KEY, JSON.stringify(obj));
        }
        return removed;
    } catch {
        return 0;
    }
}
