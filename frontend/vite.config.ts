import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": resolve(__dirname, "src") },
  },
  build: {
    rollupOptions: {
      external: ["canvg", "html2canvas", "dompurify"],
    },
  },
  server: {
    port: 5173,
    proxy: {
      // VITE_API_PROXY: otro backend local (lo usa backend/scripts/e2e_flujo_paquetes.sh)
      "/api": process.env.VITE_API_PROXY ?? "http://localhost:8000",
    },
  },
});
