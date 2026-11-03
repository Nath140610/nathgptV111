/* NathGPT : service worker minimal pour les notifications (aucun cache : le site reste toujours à jour). */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

// Notifications push envoyées par le serveur (ex. stickers Cricut prêts), même app fermée.
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data?.text() || '' }; }
  event.waitUntil(self.registration.showNotification(data.title || 'NathGPT', {
    body: data.body || '',
    icon: '/logo.png',
    badge: '/logo.png',
    tag: data.tag || 'nathgpt',
    data: { view: data.view || '', chatId: data.chatId || '' },
  }));
});

// Toucher une notification rouvre l'app au bon endroit (conversation ou panneau Cricut).
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const chatId = event.notification.data?.chatId || '';
  const view = event.notification.data?.view || '';
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      client.postMessage(view ? { type: 'open-view', view } : { type: 'open-chat', chatId });
      if ('focus' in client) return client.focus();
    }
    if (view) return self.clients.openWindow(`/?view=${encodeURIComponent(view)}`);
    return self.clients.openWindow(chatId ? `/?chat=${encodeURIComponent(chatId)}` : '/');
  })());
});
