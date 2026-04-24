<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { ICON_CACHE_KEY as CACHE_KEY, iconCacheVersion, sweepExpiredEntries } from "../icon_cache";
import { apiUrl } from "../runtime_config";

const props = defineProps<{
  url?: string;
  name?: string;
  reachability?: "up" | "down" | "unknown";
  class?: string;
}>();

// Icon cache: { [domain]: { src, fetchedAt, w, h } | null }
// - value === null marks "all sources failed — retry next session"
// - we persist width/height so we can re-validate and skip sources that returned
//   a 0-sized transparent/redirect pixel previously.
const CACHE_MAX_AGE = 30 * 24 * 60 * 60 * 1000; // 30 days
const MIN_ICON_PX = 8;
let sweptOnce = false;

type CacheEntry = { src: string; fetchedAt: number; w?: number; h?: number };

function getCache(): Record<string, CacheEntry | null> {
  try {
    return JSON.parse(localStorage.getItem(CACHE_KEY) || "{}");
  } catch {
    return {};
  }
}

function setCache(domain: string, entry: CacheEntry | null) {
  const cache = getCache();
  cache[domain] = entry;
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
  } catch {
    // localStorage full, ignore
  }
}

function getCachedIcon(domain: string): CacheEntry | null | undefined {
  const cache = getCache();
  const entry = cache[domain];
  if (entry === null) return undefined; // previous fail — allow retry
  if (entry && Date.now() - entry.fetchedAt < CACHE_MAX_AGE) return entry;
  return undefined;
}

const domain = computed(() => {
  if (!props.url) return "";
  try {
    return new URL(props.url).hostname;
  } catch {
    return "";
  }
});

const origin = computed(() => {
  if (!props.url) return "";
  try {
    return new URL(props.url).origin;
  } catch {
    return "";
  }
});

/**
 * Source priority:
 *
 * 1. `/api/sites/icon?domain=…` — server-side proxy that fetches the origin's
 *    `/favicon.ico` through the redirect guard. When the origin redirects
 *    off-site (hijack / takedown → someone else's favicon) the backend returns
 *    204 so this source fails and we fall through. This is the key fix for
 *    sites like xingyunge that redirect to unrelated domains — the browser's
 *    `<img>` tag silently follows such redirects, but our proxy doesn't.
 * 2. DuckDuckGo's icon service — keeps a record of most mainstream PT sites'
 *    canonical icons, so it's a solid fallback when origin is dead/hijacked.
 * 3. Google's s2 favicons — final fallback, covers the long tail.
 *
 * Unreachable sites still benefit from step 1 because the backend proxy will
 * either serve the real icon (if probing /favicon.ico works despite the
 * homepage being flaky) or cleanly 204 so we fall through faster.
 */
const sources = computed(() => {
  if (!domain.value) return [] as string[];
  return [
    apiUrl(`/api/sites/icon?domain=${encodeURIComponent(domain.value)}`),
    `https://icons.duckduckgo.com/ip3/${domain.value}.ico`,
    `https://www.google.com/s2/favicons?domain=${domain.value}&sz=64`,
  ];
});

const displaySrc = ref<string | null>(null);

/**
 * Deterministic color + initials fallback.
 *
 * When the favicon chain is still loading, or when every source 204'd, the
 * old Globe icon made every site look identical — a wall of gray planets.
 * Picking a hue from a cheap hash of the domain means each site gets a
 * stable, distinct swatch that's already visible before any network request
 * finishes; the real favicon fades in on top once it arrives.
 *
 * Luminance is fixed so light/dark themes both have enough contrast for the
 * white initials on top to stay readable (WCAG AA at 4.5:1 against a 55%
 * lightness background).
 */
function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

const displayName = computed(() => (props.name || domain.value || "").trim());

const initials = computed(() => {
  const n = displayName.value;
  if (!n) return "?";
  // CJK chars: take the first character. Latin: take the first 1-2 letters of the first word.
  const firstChar = n.charCodeAt(0);
  if (firstChar >= 0x3000) return n.charAt(0);
  const word = n.split(/[\s·\-._/]+/)[0] || n;
  return word.slice(0, 2).toUpperCase();
});

const fallbackStyle = computed(() => {
  const key = domain.value || displayName.value || "";
  if (!key) return {};
  const hue = hashString(key) % 360;
  return {
    backgroundColor: `hsl(${hue} 55% 50%)`,
  } as Record<string, string>;
});

function tryLoad(src: string): Promise<{ src: string; w: number; h: number } | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.referrerPolicy = "no-referrer";
    img.onload = () => {
      // Validate a real image came back — some hijacks / 404-as-image handlers
      // return a 1x1 transparent pixel which looks "loaded" but is useless.
      const w = img.naturalWidth || 0;
      const h = img.naturalHeight || 0;
      if (w < MIN_ICON_PX || h < MIN_ICON_PX) resolve(null);
      else resolve({ src, w, h });
    };
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

/**
 * Source selection is *sequential*, not parallel: we want the backend proxy's
 * verdict to take priority over external icon services. Firing all three in
 * parallel would let a fast DuckDuckGo response beat a proxy that's about to
 * serve the site's real icon — cache would then lock in the generic external
 * icon for 30 days. Walking the list one source at a time keeps the ordering
 * honest at the cost of adding ~the time of one extra HTTP round trip when
 * the proxy fails.
 */
async function loadIcons() {
  const d = domain.value;
  if (!d) {
    displaySrc.value = null;
    return;
  }

  const cached = getCachedIcon(d);
  if (cached && cached.src) {
    displaySrc.value = cached.src;
    return;
  }

  for (const src of sources.value) {
    const result = await tryLoad(src);
    if (!result) continue;
    displaySrc.value = result.src;
    setCache(d, { src: result.src, fetchedAt: Date.now(), w: result.w, h: result.h });
    return;
  }
  setCache(d, null);
}

watch([() => props.url, () => props.reachability], () => {
  displaySrc.value = null;
  void loadIcons();
});

// React to a manual "clear icon cache" from the Config page — bumping the
// shared ref forces every mounted SiteIcon to drop its in-memory src and refetch.
// No page reload required, no waiting for 30-day TTL.
watch(iconCacheVersion, () => {
  displaySrc.value = null;
  void loadIcons();
});

onMounted(() => {
  if (!sweptOnce) {
    // Best-effort opportunistic GC: on first SiteIcon mount per page load,
    // remove entries older than the TTL so abandoned domains don't accumulate.
    sweepExpiredEntries(CACHE_MAX_AGE);
    sweptOnce = true;
  }
  void loadIcons();
});
</script>

<template>
  <div :class="['relative flex flex-shrink-0 items-center justify-center overflow-hidden rounded-full', props.class]" :style="fallbackStyle">
    <!-- Initials layer renders immediately (no network required) so the list
         never looks like a wall of generic placeholders while favicons fetch. -->
    <span class="select-none text-[40%] font-bold text-white/95" aria-hidden="true">
      {{ initials }}
    </span>
    <!-- Real favicon fades in on top of the initials swatch once a valid source
         resolves; stays above via z-index. Hidden when nothing loaded so the
         initials alone carry the site's identity. -->
    <img
      v-if="displaySrc"
      :src="displaySrc"
      :alt="name || domain"
      loading="lazy"
      decoding="async"
      class="absolute inset-0 h-full w-full object-cover opacity-100 transition-opacity duration-300"
      referrerpolicy="no-referrer"
    />
  </div>
</template>
