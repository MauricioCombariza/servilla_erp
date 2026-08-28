import { readFileSync } from "fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

const CERT_DIR =
  "/tmp/claude-1000/-mnt-c-Users-mcomb-Desktop-Carvajal-python-servilla-erp/9e81f5af-06d7-4577-aafe-a7cd639b20e6/scratchpad";
const HOST = "desktop-iv4kgdk.taila76b60.ts.net";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": resolve(__dirname, "src") },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    https: {
      cert: readFileSync(`${CERT_DIR}/${HOST}.crt`),
      key: readFileSync(`${CERT_DIR}/${HOST}.key`),
    },
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
