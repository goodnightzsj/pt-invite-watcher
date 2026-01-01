<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { Globe } from "lucide-vue-next";

const props = defineProps<{
  url?: string;
  name?: string;
  class?: string;
}>();

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

// Priority list:
// 1. Direct /favicon.ico (Preferred)
// 2. DuckDuckGo (Fallback 1)
// 3. Google S2 (Fallback 2)
const sources = computed(() => {
    if (!domain.value) return [];
    return [
        `${origin.value}/favicon.ico`,
        `https://icons.duckduckgo.com/ip3/${domain.value}.ico`,
        `https://www.google.com/s2/favicons?domain=${domain.value}&sz=64`
    ];
});

// Track status of each source: 'pending', 'success', 'error'
const sourceStatus = ref<('pending' | 'success' | 'error')[]>([]);

// Determine the best src to display based on priority and success status
const displaySrc = computed(() => {
    const list = sources.value;
    const status = sourceStatus.value;
    
    // Find highest priority source that succeeded
    for (let i = 0; i < list.length; i++) {
        if (status[i] === 'success') {
            return list[i];
        }
    }
    return null;
});

function loadIcons() {
    const list = sources.value;
    sourceStatus.value = list.map(() => 'pending');

    list.forEach((src, index) => {
        const img = new Image();
        img.referrerPolicy = "no-referrer";
        img.onload = () => {
            sourceStatus.value[index] = 'success';
        };
        img.onerror = () => {
            sourceStatus.value[index] = 'error';
        };
        img.src = src;
    });
}

watch(() => props.url, () => {
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
