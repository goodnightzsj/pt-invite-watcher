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
 * Source ordering is reachability-aware:
 *
 * - When the site is known unreachable (probe flagged redirect/hijack), the
 *   origin's `/favicon.ico` is highly suspect — a parked/redirected page may
 *   serve the hijacker's icon, which we'd then cache for 30 days as the "real"
 *   icon. Skip origin entirely and rely on external icon services that
 *   remember the site's genuine favicon from its healthy days.
 * - For healthy or unknown sites, try origin first (freshest, correct colors).
 */
const sources = computed(() => {
  if (!domain.value) return [] as string[];
  const external = [
    `https://icons.duckduckgo.com/ip3/${domain.value}.ico`,
    `https://www.google.com/s2/favicons?domain=${domain.value}&sz=64`,
  ];
  if (props.reachability === "down") {
    return external;
  }
  return [`${origin.value}/favicon.ico`, ...external];
});

const displaySrc = ref<string | null>(null);

function loadIcons() {
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

  const list = sources.value;
  let resolved = false;
  let pendingFailures = 0;

  list.forEach((src) => {
    const img = new Image();
    img.referrerPolicy = "no-referrer";
    img.onload = () => {
      if (resolved) return;
      // Validate a real image came back — some hijacks / 404-as-image handlers
      // return a 1x1 transparent pixel which looks "loaded" but is useless.
      const w = img.naturalWidth || 0;
      const h = img.naturalHeight || 0;
      if (w < MIN_ICON_PX || h < MIN_ICON_PX) {
        pendingFailures += 1;
        if (pendingFailures >= list.length) setCache(d, null);
        return;
      }
      resolved = true;
      displaySrc.value = src;
      setCache(d, { src, fetchedAt: Date.now(), w, h });
    };
    img.onerror = () => {
      if (resolved) return;
      pendingFailures += 1;
      if (pendingFailures >= list.length) setCache(d, null);
    };
    img.src = src;
  });
}

watch([() => props.url, () => props.reachability], () => {
  displaySrc.value = null;
  loadIcons();
});

onMounted(() => {
  loadIcons();
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
