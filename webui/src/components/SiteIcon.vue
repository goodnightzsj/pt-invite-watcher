<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { Globe } from "lucide-vue-next";

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
const CACHE_KEY = "ptiw_icon_cache";
const CACHE_MAX_AGE = 30 * 24 * 60 * 60 * 1000; // 30 days
const MIN_ICON_PX = 8;

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
    `/api/sites/icon?domain=${encodeURIComponent(domain.value)}`,
    `https://icons.duckduckgo.com/ip3/${domain.value}.ico`,
    `https://www.google.com/s2/favicons?domain=${domain.value}&sz=64`,
  ];
});

const displaySrc = ref<string | null>(null);

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

onMounted(() => {
  void loadIcons();
});
</script>

<template>
  <div :class="['relative flex flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800', props.class]">
    <img
      v-if="displaySrc"
      :src="displaySrc"
      :alt="name || domain"
      loading="lazy"
      decoding="async"
      class="h-full w-full object-cover opacity-90 transition-opacity duration-300"
      referrerpolicy="no-referrer"
    />
    <Globe v-else class="h-1/2 w-1/2 text-slate-300 dark:text-slate-600" />
  </div>
</template>
