<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { Globe } from "lucide-vue-next";

const props = defineProps<{
  url?: string;
  name?: string;
  class?: string;
}>();

// Icon cache: { [domain]: { src: string, fetchedAt: number } | null }
// null means all sources failed (will retry on next session)
const CACHE_KEY = "ptiw_icon_cache";
const CACHE_MAX_AGE = 30 * 24 * 60 * 60 * 1000; // 30 days

function getCache(): Record<string, { src: string; fetchedAt: number } | null> {
  try {
    return JSON.parse(localStorage.getItem(CACHE_KEY) || "{}");
  } catch {
    return {};
  }
}

function setCache(domain: string, src: string | null) {
  const cache = getCache();
  if (src) {
    cache[domain] = { src, fetchedAt: Date.now() };
  } else {
    cache[domain] = null; // Mark as failed
  }
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
  } catch {
    // localStorage full, ignore
  }
}

function getCachedIcon(domain: string): string | null | undefined {
  const cache = getCache();
  const entry = cache[domain];
  if (entry === null) {
    // Failed before, can retry
    return undefined;
  }
  if (entry && Date.now() - entry.fetchedAt < CACHE_MAX_AGE) {
    return entry.src;
  }
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

const sources = computed(() => {
  if (!domain.value) return [];
  return [
    `${origin.value}/favicon.ico`,
    `https://icons.duckduckgo.com/ip3/${domain.value}.ico`,
    `https://www.google.com/s2/favicons?domain=${domain.value}&sz=64`
  ];
});

const displaySrc = ref<string | null>(null);

function loadIcons() {
  const d = domain.value;
  if (!d) {
    displaySrc.value = null;
    return;
  }

  // Check cache first
  const cached = getCachedIcon(d);
  if (cached) {
    displaySrc.value = cached;
    return;
  }

  // If cached === null (failed before), don't retry in same session
  // If cached === undefined, try fetching

  const list = sources.value;
  let resolved = false;

  list.forEach((src, index) => {
    const img = new Image();
    img.referrerPolicy = "no-referrer";
    img.onload = () => {
      if (!resolved) {
        resolved = true;
        displaySrc.value = src;
        setCache(d, src);
      }
    };
    img.onerror = () => {
      // If all failed, mark as null
      if (index === list.length - 1 && !resolved) {
        // Last source failed
        setTimeout(() => {
          if (!resolved) {
            setCache(d, null);
          }
        }, 500);
      }
    };
    img.src = src;
  });
}

watch(() => props.url, () => {
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
      class="h-full w-full object-cover opacity-90 transition-opacity duration-300"
      referrerpolicy="no-referrer"
    />
    <Globe v-else class="h-1/2 w-1/2 text-slate-300 dark:text-slate-600" />
  </div>
</template>
