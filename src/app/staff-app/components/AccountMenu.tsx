'use client'

// Account controls for the phone app.
//
// /staff-app is CHROMELESS (see navRoutes.ts), so it never renders the desktop
// TopNav - which is where sign-out and the language toggle live. A FRONTLINE
// account holds no desktop route at all, so for a care worker that shell is not
// "the other layout", it is the only one they will ever see: without this the app
// has no way out and no way to switch language.
import { useEffect, useRef, useState } from 'react'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth, roleLabel } from '@/components/layout/AuthContext'

const PINK = '#e87a8e'

export default function AccountMenu() {
  const [open, setOpen] = useState(false)
  const { lang, setLang, t } = useLang()
  const { user, signOut } = useAuth()
  const isZH = lang === 'zh'
  const closeRef = useRef<HTMLButtonElement>(null)

  // Esc closes, same as the backdrop tap. A phone keyboard rarely sends it, but
  // the app is also opened on a desktop browser during training.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const initial =
    user?.email?.charAt(0).toUpperCase() ?? 'U'

  return (
    <div className="flex items-center gap-2">
      {/* Language toggle, deliberately always visible rather than buried in the
          menu: switching language is the first thing a non-Chinese-reading agency
          worker needs, and they cannot read the label on the menu that hides it. */}
      <button
        type="button"
        onClick={() => setLang(isZH ? 'en' : 'zh')}
        aria-label={t('sa_language')}
        className="rounded-lg border px-2 py-1 text-[11px] font-semibold transition-colors"
        style={{ borderColor: PINK, color: PINK, background: '#fff5f7' }}
      >
        {isZH ? 'EN' : '中'}
      </button>

      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={t('sa_account')}
          className="flex h-9 w-9 items-center justify-center rounded-full text-xs font-semibold text-white transition-opacity active:opacity-80"
          style={{ background: PINK }}
        >
          {initial}
        </button>

        {open && (
          <>
            <button
              className="fixed inset-0 z-40 cursor-default"
              aria-hidden
              tabIndex={-1}
              onClick={() => setOpen(false)}
            />
            <div
              role="menu"
              className="absolute right-0 top-full z-50 mt-2 w-60 rounded-2xl border border-gray-200 bg-white p-1 shadow-lg"
            >
              <div className="px-3 py-2">
                <p className="text-[10px] text-gray-400">{t('sa_signed_in_as')}</p>
                <p className="truncate text-xs font-semibold text-gray-800">{user?.email ?? '-'}</p>
                <p className="mt-0.5 truncate text-[10px] text-gray-500">
                  {user?.facilityName}
                  {user?.role ? ` · ${roleLabel(user.role, isZH)}` : ''}
                </p>
              </div>

              <div className="my-1 h-px bg-gray-100" />

              <div className="flex items-center justify-between px-3 py-2">
                <span className="text-xs font-medium text-gray-700">{t('sa_language')}</span>
                <div className="flex overflow-hidden rounded-lg border border-gray-200">
                  {(['en', 'zh'] as const).map((code) => (
                    <button
                      key={code}
                      type="button"
                      onClick={() => setLang(code)}
                      className="px-2.5 py-1 text-[11px] font-semibold transition-colors"
                      style={{
                        background: lang === code ? '#fdecef' : '#fff',
                        color: lang === code ? PINK : '#6b7280',
                      }}
                    >
                      {code === 'en' ? 'EN' : '中文'}
                    </button>
                  ))}
                </div>
              </div>

              <div className="my-1 h-px bg-gray-100" />

              <button
                ref={closeRef}
                type="button"
                role="menuitem"
                onClick={() => { setOpen(false); signOut() }}
                className="w-full rounded-xl px-3 py-2 text-left text-xs font-semibold text-rose-600 transition-colors hover:bg-rose-50"
              >
                {t('sa_sign_out')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
