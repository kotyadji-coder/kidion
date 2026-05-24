// Minimal service worker for PWA install prompt
self.addEventListener('install', function(e) {
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(clients.claim());
});

self.addEventListener('fetch', function(e) {
  // Network-first: don't cache, just pass through
  // This is intentionally minimal — we only need SW for PWA installability
});
