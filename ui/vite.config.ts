import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const design = fileURLToPath(new URL("../src/metamorph/design", import.meta.url));

// The build lands inside the Python package so `metamorph serve` ships the UI with no Node.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@design": design } },
  build: {
    outDir: fileURLToPath(new URL("../src/metamorph/server/static", import.meta.url)),
    emptyOutDir: true,
  },
  server: {
    fs: { allow: [".", design] },
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
