/* NathGPT : service worker minimal pour les notifications (aucun cache : le site reste toujours à jour). */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

// Toucher une notification rouvre l'app sur la bonne conversation.
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const chatId = event.notification.data?.chatId || '';
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      client.postMessage({ type: 'open-chat', chatId });
      if ('focus' in client) return client.focus();
    }
    return self.clients.openWindow(chatId ? `/?chat=${encodeURIComponent(chatId)}` : '/');
  })());
});
