import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/api": {
        // Use 127.0.0.1 to avoid IPv6 ::1 issues on macOS when "localhost" resolves to IPv6.
        target: process.env.PTIW_DEV_API_TARGET || "http://127.0.0.1:8080",
        changeOrigin: true,
      },
      "/ws": {
        target: process.env.PTIW_DEV_WS_TARGET || "ws://127.0.0.1:8080",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: resolve(__dirname, "../pt_invite_watcher/webui_dist"),
    emptyOutDir: true,
    // Split big vendor bundles so the initial JS payload streams faster on slow networks.
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ["vue", "vue-router"],
          icons: ["lucide-vue-next"],
        },
      },
    },
  },
});
