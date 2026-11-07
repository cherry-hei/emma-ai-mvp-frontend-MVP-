import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

/**
 * This SPA never registers a service worker. Clear legacy registrations and
 * Cache Storage on startup so an earlier demo worker cannot retain auth/API or
 * private staff responses after the portable build is deployed.
 */
async function clearLegacyOfflineState() {
  if ("serviceWorker" in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((registration) => registration.unregister()));
  }
  if ("caches" in window) {
    const keys = await caches.keys();
    await Promise.all(keys.map((key) => caches.delete(key)));
  }
}

void clearLegacyOfflineState().catch(() => {
  // A blocked cleanup must not make the authenticated app unusable.
});

createRoot(document.getElementById("root")!).render(<App />);
