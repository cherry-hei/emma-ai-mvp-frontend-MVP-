// src/lib/push.ts
// Web push registration for the Staff PWA (spec SA.4b).
//
// The backend half of SA.4 has been able to send since the FCM sender landed;
// what was missing was a device to send to. This asks the browser for
// permission, gets an FCM registration token, and hands it to
// POST /me/push-subscriptions so `push.deliver()` has somewhere to deliver.
//
// Everything here is deliberately soft-failing. Push is the extra that reaches a
// care worker whose phone is in a pocket; the in-app notification list is the
// guarantee. A blocked permission, an unsupported browser, or an unprovisioned
// Firebase project must leave the app fully usable - so every path returns a
// reason instead of throwing.
//
// Configuration comes from NEXT_PUBLIC_FIREBASE_* (see .env.example). Until the
// Firebase project exists those are unset and `enablePush()` reports
// 'not_configured' without prompting the user for a permission we cannot honour.
import { api } from './api'

export type PushOutcome =
  | 'subscribed'        // token registered with the backend
  | 'not_configured'    // no Firebase project wired up yet
  | 'unsupported'       // browser has no service worker / Notification API
  | 'denied'            // the user said no
  | 'dismissed'         // the user closed the prompt without deciding
  | 'failed'            // something else went wrong; details in the console

export interface PushConfig {
  apiKey: string
  projectId: string
  messagingSenderId: string
  appId: string
  vapidKey: string
}

/** The env-var block, or null when the Firebase project has not been provisioned. */
export function pushConfig(): PushConfig | null {
  const cfg = {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || '',
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || '',
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || '',
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID || '',
    // The VAPID public key, from Firebase console → Cloud Messaging → Web Push
    // certificates. Web push tokens cannot be minted without it.
    vapidKey: process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY || '',
  }
  return Object.values(cfg).every(Boolean) ? cfg : null
}

export function pushSupported(): boolean {
  return typeof window !== 'undefined'
    && 'serviceWorker' in navigator
    && 'Notification' in window
    && 'PushManager' in window
}

/**
 * Register this device for push. Safe to call on every app launch: the backend
 * upserts on the token, and the browser returns the same token until the user
 * clears site data.
 *
 * Only called from a user gesture in the UI - Chrome ignores (and Safari
 * outright refuses) a permission prompt that is not tied to one, and a prompt on
 * first paint is the one users reflexively block.
 */
export async function enablePush(): Promise<PushOutcome> {
  if (!pushSupported()) return 'unsupported'
  const cfg = pushConfig()
  if (!cfg) return 'not_configured'

  try {
    const permission = await Notification.requestPermission()
    if (permission === 'denied') return 'denied'
    if (permission !== 'granted') return 'dismissed'

    // The service worker needs the config too, and a worker script cannot read
    // process.env - it is served as a static file, not built by Next. Passed as
    // query params so one checked-in worker serves every environment.
    const params = new URLSearchParams({
      apiKey: cfg.apiKey,
      projectId: cfg.projectId,
      messagingSenderId: cfg.messagingSenderId,
      appId: cfg.appId,
    })
    const registration = await navigator.serviceWorker.register(
      `/firebase-messaging-sw.js?${params.toString()}`,
      { scope: '/' },
    )

    // Dynamic import: the Firebase SDK is ~90 kB and only reached by a staff
    // member who has opted into notifications, so it stays out of the app's
    // first load.
    const { initializeApp, getApps } = await import('firebase/app')
    const { getMessaging, getToken } = await import('firebase/messaging')
    const app = getApps()[0] ?? initializeApp(cfg)

    const token = await getToken(getMessaging(app), {
      vapidKey: cfg.vapidKey,
      serviceWorkerRegistration: registration,
    })
    if (!token) return 'failed'

    await api.registerPushDevice({
      token,
      platform: 'web',
      user_agent: navigator.userAgent,
    })
    return 'subscribed'
  } catch (e) {
    // Includes the unprovisioned-project case, where getToken rejects rather
    // than returning empty. Logged rather than surfaced: there is nothing the
    // staff member can do about it, and the app still works without push.
    console.warn('[push] could not subscribe this device', e)
    return 'failed'
  }
}

/** Whether this browser has already been granted notification permission. */
export function pushPermission(): NotificationPermission | 'unsupported' {
  return pushSupported() ? Notification.permission : 'unsupported'
}

/**
 * Re-register silently on launch when permission was granted on a previous
 * visit. FCM rotates tokens (reinstall, cleared storage, key refresh), and a
 * rotated token means the backend is holding one that no longer routes anywhere.
 * No prompt is possible here, so a failure is genuinely nothing to report.
 */
export async function refreshPushSubscription(): Promise<PushOutcome> {
  if (pushPermission() !== 'granted') return 'dismissed'
  return enablePush()
}
