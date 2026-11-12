import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Python server (`kestrel watch`) serves the built app and the API.
// In development, `npm run dev` proxies /api and /previews to it.
const api = `http://127.0.0.1:${process.env.KESTREL_PORT || 7777}`;
const proxy = { target: api, changeOrigin: true, headers: { Origin: api } };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { proxy: { "/api": proxy, "/previews": proxy } },
  build: {
    outDir: "../src/kestrel/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 700,
  },
});
