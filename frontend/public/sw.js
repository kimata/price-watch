// Service Worker for Web Push Notifications
// Price Watch - Push Notification Handler

const CACHE_NAME = "price-watch-v1";

// Install event - cache necessary assets
self.addEventListener("install", (event) => {
    console.log("[SW] Installing Service Worker");
    self.skipWaiting();
});

// Activate event - cleanup old caches
self.addEventListener("activate", (event) => {
    console.log("[SW] Activating Service Worker");
    event.waitUntil(
        caches
            .keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
                );
            })
            .then(() => {
                return self.clients.claim();
            })
    );
});

// Push event - handle incoming push notifications
self.addEventListener("push", (event) => {
    console.log("[SW] Push received:", event);

    let data = {
        title: "Price Watch",
        body: "価格が変動しました",
        tag: "price-watch-notification",
    };

    if (event.data) {
        try {
            data = { ...data, ...event.data.json() };
        } catch (e) {
            console.error("[SW] Failed to parse push data:", e);
            data.body = event.data.text();
        }
    }

    const options = {
        body: data.body,
        icon: "/price/logo.svg",
        badge: "/price/logo.svg",
        tag: data.tag || "price-watch-notification",
        renotify: true,
        requireInteraction: false,
        data: {
            url: data.url || "/price/",
        },
    };

    event.waitUntil(self.registration.showNotification(data.title, options));
});

// Notification click event - open the relevant page
self.addEventListener("notificationclick", (event) => {
    console.log("[SW] Notification clicked:", event);

    event.notification.close();

    const urlToOpen = event.notification.data?.url || "/price/";

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
            // Check if a window is already open on the target URL
            for (const client of clientList) {
                if (client.url.includes("/price/") && "focus" in client) {
                    return client.focus().then((focusedClient) => {
                        if (focusedClient && "navigate" in focusedClient) {
                            return focusedClient.navigate(urlToOpen);
                        }
                    });
                }
            }
            // If no window is open, open a new one
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});

// Push subscription change event - handle subscription changes
self.addEventListener("pushsubscriptionchange", (event) => {
    console.log("[SW] Push subscription changed:", event);
    // The subscription has changed - the app should re-subscribe
    // This is handled by the frontend when the user visits the page
});
