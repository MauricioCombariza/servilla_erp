import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import legacy from "@vitejs/plugin-legacy";
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
  plugins: [
    react(),
    // iPhones viejos (Safari/Chrome de iOS <= 15 usan el mismo motor): sin esto la app queda
    // en blanco. Genera un bundle "nomodule" con polyfills, y modernPolyfills cubre iOS 15.0-15.3
    // (cargan el bundle moderno pero no tienen Object.hasOwn ni Array.prototype.at).
    legacy({ targets: ["defaults", "iOS >= 12"], modernPolyfills: true }),
    archivoVersion(),
  ],
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
      // VITE_FLUJO_PROXY: el servicio Go (flujo/) para las mismas rutas que le manda nginx
      // en producción (infra/nginx.conf). Sin él, todo va a FastAPI.
      ...(process.env.VITE_FLUJO_PROXY
        ? {
            "^/api/(tulas|asignacion-zonas|asignacion-qr|imile-sesion|flujo)(/|$)": process.env.VITE_FLUJO_PROXY,
            "^/api/paquetes-despacho/(destino/|base$)": process.env.VITE_FLUJO_PROXY,
          }
        : {}),
      // VITE_API_PROXY: otro backend local (lo usa backend/scripts/e2e_flujo_paquetes.sh)
      "/api": process.env.VITE_API_PROXY ?? "http://localhost:8000",
    },
  },
});
