const CACHE_NAME = "nathgpt-shell-v5";
const APP_SHELL = [
    "/static/style.css",
    "/static/manifest.webmanifest?v=5",
    "/logo.png?v=5"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(APP_SHELL))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const destination = event.notification.data?.url || "/";
    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true })
            .then((windows) => {
                const existing = windows.find((windowClient) =>
                    new URL(windowClient.url).origin === self.location.origin
                );
                if (existing) {
                    return existing.navigate(destination).then(() => existing.focus());
                }
                return clients.openWindow(destination);
            })
    );
});

self.addEventListener("push", (event) => {
    let data = {};
    try {
        data = event.data?.json() || {};
    }
    catch (_) {
        data = {};
    }
    event.waitUntil(self.registration.showNotification(data.title || "NathGPT", {
        body: data.body || "Ta génération est prête.",
        icon: "/logo.png?v=5",
        badge: "/logo.png?v=5",
        tag: data.conversation_id || "nathgpt-notification",
        renotify: true,
        vibrate: [120, 55, 120],
        data: {
            url: data.url || "/",
            conversation_id: data.conversation_id || ""
        }
    }));
});
