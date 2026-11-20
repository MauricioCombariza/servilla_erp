import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);

// Que la app abra sin señal (ver public/sw.js). Solo en producción: en desarrollo estorbaría a Vite.
// En iPhone/iPad no (Safari 27 no carga la app con un service worker activo; ver index.html).
const sinServiceWorker = (window as unknown as { __sinServiceWorker?: boolean }).__sinServiceWorker;
if (import.meta.env.PROD && "serviceWorker" in navigator && !sinServiceWorker) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
