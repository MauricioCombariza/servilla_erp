import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Número de esta compilación: va dentro del código y en /version.json. La app compara los
// dos para saber si se desplegó una versión nueva (src/components/AlDia.tsx).
const VERSION = new Date().toISOString();

function archivoVersion(): Plugin {
  return {
    name: "archivo-version",
    apply: "build",
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "version.json", source: JSON.stringify({ version: VERSION }) });
    },
  };
}

export default defineConfig({
  plugins: [react(), archivoVersion()],
  define: { __APP_VERSION__: JSON.stringify(VERSION) },
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
