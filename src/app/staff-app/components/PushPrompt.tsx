'use client'

// Opt-in banner for push notifications (spec SA.4b).
//
// Deliberately a banner with a button rather than a prompt on first paint:
// Chrome ignores a permission request that is not tied to a user gesture, and
// Safari refuses one outright. A prompt the user did not ask for is also the one
// they reflexively block, and a blocked permission cannot be re-requested from
// the page - it needs a trip into browser settings. So we explain first, and ask
// once they tap.
//
// Renders nothing at all when there is nothing to ask for: no Firebase project
// configured, an unsupported browser, or permission already decided.
import { useEffect, useState } from 'react'
import { enablePush, pushConfig, refreshPushSubscription } from '@/lib/push'
import { useLang } from '@/components/layout/LanguageContext'

const DISMISS_KEY = 'emma_push_dismissed'

export default function PushPrompt() {
  const { t } = useLang()
  const [visible, setVisible] = useState(false)
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<'denied' | 'failed' | null>(null)

  useEffect(() => {
    if (!pushConfig()) return                       // not provisioned yet
    let cancelled = false

    function apply(permission: NotificationPermission) {
      if (cancelled) return
      if (permission === 'granted') {
        // Already allowed on a previous visit. Re-register silently, because FCM
        // rotates tokens and the backend may be holding one that no longer
        // routes to this phone.
        setVisible(false)
        void refreshPushSubscription()
        return
      }
      setVisible(permission === 'default'
        && window.localStorage.getItem(DISMISS_KEY) !== '1')
    }

    // Read through navigator.permissions rather than Notification.permission so
    // we also get its change event: a staff member who grants the permission in
    // browser settings should see this banner go away without a reload.
    navigator.permissions?.query({ name: 'notifications' as PermissionName })
      .then((status) => {
        const toPermission = (state: PermissionState): NotificationPermission =>
          state === 'prompt' ? 'default' : state
        apply(toPermission(status.state))
        status.onchange = () => apply(toPermission(status.state))
      })
      // Safari before 16 has no notifications entry in the permissions registry.
      .catch(() => apply(Notification.permission))

    return () => { cancelled = true }
  }, [])

  async function onEnable() {
    setBusy(true)
    const result = await enablePush()
    setBusy(false)
    if (result === 'subscribed') return setVisible(false)
    if (result === 'denied') return setOutcome('denied')
    if (result === 'dismissed') return                // prompt closed; ask again later
    setOutcome('failed')
  }

  function onDismiss() {
    window.localStorage.setItem(DISMISS_KEY, '1')
    setVisible(false)
  }

  if (!visible) return null

  return (
    <div className="mb-4 rounded-2xl border border-[#f6d3da] bg-[#fdf4f6] p-4">
      <p className="text-sm font-semibold text-gray-900">{t('sa_push_title')}</p>
      <p className="mt-1 text-xs leading-relaxed text-gray-600">{t('sa_push_body')}</p>

      {outcome === 'denied' && (
        <p className="mt-2 text-xs text-rose-600">{t('sa_push_denied')}</p>
      )}
      {outcome === 'failed' && (
        <p className="mt-2 text-xs text-rose-600">{t('sa_push_failed')}</p>
      )}

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={onEnable}
          disabled={busy || outcome === 'denied'}
          className="rounded-xl bg-[#e87a8e] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
        >
          {busy ? t('sa_push_working') : t('sa_push_enable')}
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-xl px-3 py-2 text-xs font-medium text-gray-500"
        >
          {t('sa_push_later')}
        </button>
      </div>
    </div>
  )
}
