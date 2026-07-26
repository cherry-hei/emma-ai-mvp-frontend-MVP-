'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/layout/AuthContext'
import { useLang } from '@/components/layout/LanguageContext'

const PINK = '#E8187A'

// Seeded local-dev accounts (see emma-ai-app/scripts/seed.py). Handy for switching
// between Home A and Home B while there is no self-service account management.
const DEMO_ACCOUNTS = [
  { email: 'super_a@emma.local', facility: 'Home A', roleEN: 'Superintendent', roleZH: '院長' },
  { email: 'admin_a@emma.local', facility: 'Home A', roleEN: 'Admin',          roleZH: '管理員' },
  { email: 'super_b@emma.local', facility: 'Home B', roleEN: 'Superintendent', roleZH: '院長' },
]
// Dev conveniences (form prefill + one-click demo accounts) are compiled in only for
// local `next dev`, or when a non-prod deploy explicitly opts in via
// NEXT_PUBLIC_ENABLE_DEV_LOGIN=true. Production builds ship a bare email/password
// form with no seeded credentials in the bundle.
const DEV_LOGIN =
  process.env.NODE_ENV !== 'production' ||
  process.env.NEXT_PUBLIC_ENABLE_DEV_LOGIN === 'true'
const DEV_EMAIL = DEV_LOGIN ? (process.env.NEXT_PUBLIC_DEV_EMAIL || '') : ''
const DEV_PASSWORD = DEV_LOGIN ? (process.env.NEXT_PUBLIC_DEV_PASSWORD || '') : ''

export default function LoginPage() {
  const { signIn } = useAuth()
  const { lang, setLang } = useLang()
  const isZH = lang === 'zh'
  const router = useRouter()

  const [email, setEmail] = useState(DEV_EMAIL)
  const [password, setPassword] = useState(DEV_PASSWORD)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const T = {
    title:    isZH ? '登入 Emma AI'        : 'Sign in to Emma AI',
    subtitle: isZH ? '院舍更表管理系統'      : 'Care-home roster management',
    email:    isZH ? '電郵'                : 'Email',
    password: isZH ? '密碼'                : 'Password',
    signin:   isZH ? '登入'                : 'Sign in',
    signing:  isZH ? '登入中…'             : 'Signing in…',
    demo:     isZH ? '示範帳戶（本地）'      : 'Demo accounts (local)',
    demoHint: isZH ? '點擊即以該帳戶登入'    : 'Click to sign in as that account',
    failed:   isZH ? '登入失敗'            : 'Sign-in failed',
  }

  async function doSignIn(nextEmail: string, nextPassword: string) {
    setBusy(true)
    setError('')
    try {
      await signIn(nextEmail, nextPassword)
      router.replace('/dashboard')
    } catch (e) {
      setError(e instanceof Error ? e.message : T.failed)
      setBusy(false)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center p-6"
      style={{ background: 'linear-gradient(135deg,#fdf2f8 0%,#eff6ff 100%)' }}
    >
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="text-center mb-6">
          <div className="text-3xl font-bold" style={{ color: PINK, letterSpacing: '-0.5px' }}>Emma AI</div>
          <div className="text-[9px] tracking-[3px] mt-1 text-gray-400">MEDICAL INTELLIGENCE</div>
        </div>

        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-7">
          <div className="flex items-start justify-between mb-5">
            <div>
              <h1 className="text-lg font-bold text-gray-900">{T.title}</h1>
              <p className="text-xs text-gray-500 mt-0.5">{T.subtitle}</p>
            </div>
            <button
              type="button"
              onClick={() => setLang(isZH ? 'en' : 'zh')}
              className="px-2 py-1 rounded text-[11px] font-medium border"
              style={{ borderColor: PINK, color: PINK, background: '#fff5f7' }}
            >
              {isZH ? 'EN' : '中'}
            </button>
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); doSignIn(email, password) }}
            className="space-y-3"
          >
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 mb-1">{T.email}</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                placeholder="you@emma.local"
                className="w-full px-3 py-2 rounded-xl border border-gray-200 bg-gray-50 text-sm outline-none focus:border-pink-400"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 mb-1">{T.password}</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
                className="w-full px-3 py-2 rounded-xl border border-gray-200 bg-gray-50 text-sm outline-none focus:border-pink-400"
              />
            </div>

            {error && (
              <div className="rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-600">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={busy || !email || !password}
              className="w-full py-2.5 rounded-xl text-white text-sm font-semibold transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              style={{ background: PINK }}
            >
              {busy ? T.signing : T.signin}
            </button>
          </form>

          {/* Demo accounts (local dev / opt-in only) */}
          {DEV_LOGIN && (
          <div className="mt-6">
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{T.demo}</div>
            <div className="text-[10px] text-gray-400 mb-2">{T.demoHint}</div>
            <div className="space-y-1.5">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.email}
                  type="button"
                  disabled={busy || !DEV_PASSWORD}
                  onClick={() => { setEmail(a.email); setPassword(DEV_PASSWORD); doSignIn(a.email, DEV_PASSWORD) }}
                  className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-xl border border-gray-200 hover:border-pink-300 hover:bg-pink-50/50 transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <div>
                    <div className="text-xs font-semibold text-gray-800">{a.facility} · {isZH ? a.roleZH : a.roleEN}</div>
                    <div className="text-[10px] text-gray-400">{a.email}</div>
                  </div>
                  <span className="text-[11px]" style={{ color: PINK }}>→</span>
                </button>
              ))}
            </div>
          </div>
          )}
        </div>
      </div>
    </div>
  )
}
