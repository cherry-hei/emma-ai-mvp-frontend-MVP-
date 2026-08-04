/* Emma AI Staff PWA - background push handler (spec SA.4b).
 *
 * This runs when the app is closed, which is the whole point of SA.4b: a care
 * worker whose leave was approved at 22:00 finds out then, not at their next
 * launch. Foreground messages are handled in the app, not here.
 *
 * Served as a static file, so it cannot read process.env. `src/lib/push.ts`
 * registers it with the Firebase web config in the query string, which is how
 * one checked-in worker serves dev, staging and production. Those values are
 * public identifiers by design (they ship in every web client); the sending
 * credential is the service account key and stays on the server.
 *
 * The SDK is loaded from gstatic with the compat build because importScripts in
 * a service worker cannot take ES modules.
 */
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js')
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js')

const params = new URL(self.location.href).searchParams
const config = {
  apiKey: params.get('apiKey'),
  projectId: params.get('projectId'),
  messagingSenderId: params.get('messagingSenderId'),
  appId: params.get('appId'),
}

// Registered without config (a stale worker from before SA.4b, or a direct hit
// on the URL) - stay installed but inert rather than throwing on every push.
if (config.apiKey && config.messagingSenderId) {
  firebase.initializeApp(config)
  const messaging = firebase.messaging()

  messaging.onBackgroundMessage((payload) => {
    const data = payload.data || {}
    const notification = payload.notification || {}
    // `data` carries the routing pair the backend sends (see push.py); keeping it
    // on the notification means the click handler still has it after the OS has
    // held the notification in the tray for an hour.
    self.registration.showNotification(notification.title || 'Emma AI', {
      body: notification.body || '',
      icon: '/icons/emma-192.png',
      badge: '/icons/emma-badge.png',
      // Collapses repeats about the same thing: two edits to one leave request
      // should replace, not stack.
      tag: data.related_id || data.notification_id || 'emma',
      data,
    })
  })
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const data = event.notification.data || {}
  const target = routeFor(data)

  // Focus an already-open tab rather than opening a second copy of the app.
  event.waitUntil((async () => {
    const clientList = await self.clients.matchAll({
      type: 'window',
      includeUncontrolled: true,
    })
    for (const client of clientList) {
      if (client.url.includes('/staff-app')) {
        await client.focus()
        // The app listens for this and switches tab, so a focused tab lands on
        // the same screen a cold start would.
        client.postMessage({ type: 'emma:notification-click', data })
        return
      }
    }
    await self.clients.openWindow(target)
  })())
})

/** Which staff-app screen a notification should open. */
function routeFor(data) {
  switch (data.related_type) {
    case 'leave_request':
      return '/staff-app?tab=shift'
    case 'task_assignment':
      return '/staff-app?tab=tasks'
    case 'roster_version':
      return '/staff-app?tab=shift'
    default:
      return '/staff-app'
  }
}
