// Service worker: menyuya offline BAXIŞ üçün.
// Yalnız GET sorğuları və yalnız /r/ (menyu) və /media/ (şəkillər) keşlənir.
// Strategiya: əvvəl şəbəkə, alınmasa keş. Sifariş (POST) keşlənmir, internet tələb edir.
const CACHE = 'menu-v1';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith('/r/') && !url.pathname.startsWith('/media/')) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
