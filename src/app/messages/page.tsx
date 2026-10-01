'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'

interface Contact { id: string; display_name: string; role: string; staff_id?: string | null }
interface DirectMessage { id: string; sender_profile_id: string; recipient_profile_id: string; body: string; created_at: string; read_at: string | null }

export default function MessagesPage() {
  const { lang } = useLang()
  const { user } = useAuth()
  const zh = lang === 'zh'
  const [contacts, setContacts] = useState<Contact[]>([])
  const [messages, setMessages] = useState<DirectMessage[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [people, rows] = await Promise.all([
        apiFetch<Contact[]>('/messages/contacts'),
        apiFetch<DirectMessage[]>('/messages'),
      ])
      setContacts(people)
      setMessages(rows)
      setError('')
    } catch (e) {
      // Do not show fake success or reuse local mock data if the API isn't deployed.
      setContacts([])
      setMessages([])
      setSelectedId(null)
      setError(e instanceof Error ? e.message : 'Unable to load messages')
    } finally { if (!silent) setLoading(false) }
  }, [])

  useEffect(() => {
    if (!user) return
    void load()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && navigator.onLine) void load(true)
    }, 30_000)
    return () => window.clearInterval(timer)
  }, [load, user])

  const grouped = useMemo(() => {
    const known = new Set(contacts.map(c => c.id))
    return messages.filter(m => known.has(m.sender_profile_id) || known.has(m.recipient_profile_id))
  }, [contacts, messages])
  const active = contacts.find(c => c.id === selectedId)
  const thread = active ? grouped.filter(m => m.sender_profile_id === active.id || m.recipient_profile_id === active.id)
    .sort((a, b) => a.created_at.localeCompare(b.created_at)) : []
  const lastFor = (id: string) => grouped.filter(m => m.sender_profile_id === id || m.recipient_profile_id === id).at(-1)

  async function open(contact: Contact) {
    setSelectedId(contact.id)
    const unread = grouped.filter(m => m.sender_profile_id === contact.id && !m.read_at)
    for (const row of unread) {
      try { await apiFetch(`/messages/${encodeURIComponent(row.id)}/read`, { method: 'PATCH' }) }
      catch { /* Keep unread state; next refresh retries. */ }
    }
    if (unread.length) await load(true)
  }

  async function send() {
    if (!active || !input.trim() || sending) return
    setSending(true)
    try {
      await apiFetch<DirectMessage>('/messages', {
        method: 'POST', body: JSON.stringify({ recipient_profile_id: active.id, body: input.trim() }),
      })
      setInput('')
      await load(true)
    } catch (e) { setError(e instanceof Error ? e.message : 'Message not sent') }
    finally { setSending(false) }
  }

  return <div className="mx-auto flex h-full max-w-6xl flex-col gap-4 p-4 md:p-6 text-foreground">
    <header><h1 className="text-lg font-bold">{zh ? '訊息中心' : 'Messages'}</h1>
      <p className="text-xs text-muted-foreground">{zh ? '與同機構已開戶的員工雙向溝通；系統通知和替更邀請不等於聊天訊息。' : 'Two-way messages with provisioned staff in this facility; operational notices and cover offers are separate.'}</p>
      <p className="mt-1 text-xs font-medium text-rose-700 dark:text-rose-300">{zh ? '僅供合成資料測試；未完成香港正式環境審批前，請勿輸入真實員工／院友資料。' : 'Synthetic-data evaluation only. No real staff or resident details before the Hong Kong production gate.'}</p>
    </header>
    {error && <div role="alert" className="rounded-xl border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950 dark:text-rose-100">{error} · {zh ? '後端未上線或無權限；訊息沒有儲存在本機。' : 'Backend unavailable or access denied; no local message was saved.'}</div>}
    {loading ? <p className="text-sm">{zh ? '載入中…' : 'Loading…'}</p> :
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 md:grid-cols-[230px_1fr]">
        <aside className="min-h-28 overflow-y-auto rounded-xl border border-border bg-card p-2" aria-label={zh ? '可聯絡員工' : 'Contacts'}>
          {!contacts.length && <p className="p-3 text-sm text-muted-foreground">{zh ? '沒有已開戶、可聯絡的員工。' : 'No provisioned staff contacts.'}</p>}
          {contacts.map(c => { const latest = lastFor(c.id)
            return <button key={c.id} type="button" onClick={() => void open(c)} aria-pressed={selectedId === c.id}
              className={`mb-1 block w-full rounded-lg p-3 text-left text-sm ${selectedId === c.id ? 'bg-pink-100 text-pink-900 dark:bg-pink-900 dark:text-white' : 'hover:bg-accent'}`}>
              <strong className="block truncate">{c.display_name}</strong>
              <span className="block truncate text-xs text-muted-foreground">{latest?.body || (zh ? '開始對話' : 'Start conversation')}</span>
              {grouped.filter(m => m.sender_profile_id === c.id && !m.read_at).length > 0 && <span className="text-xs font-bold text-pink-700 dark:text-pink-300">{zh ? '未讀' : 'Unread'}</span>}
            </button> })}
        </aside>
        <section className="flex min-h-[360px] flex-col overflow-hidden rounded-xl border border-border bg-card">
          {active ? <>
            <div className="border-b border-border p-3 text-sm font-semibold">{active.display_name}</div>
            <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
              {!thread.length && <p className="text-sm text-muted-foreground">{zh ? '未有對話。' : 'No messages yet.'}</p>}
              {thread.map(m => { const incoming = m.sender_profile_id === active.id
                return <div key={m.id} className={`flex ${incoming ? 'justify-start' : 'justify-end'}`}>
                  <div className={`max-w-[85%] rounded-xl p-3 text-sm ${incoming ? 'bg-muted text-foreground' : 'bg-pink-600 text-white'}`}>
                    <p className="whitespace-pre-wrap break-words">{m.body}</p>
                    <time dateTime={m.created_at} className="mt-1 block text-[10px] opacity-80">{new Date(m.created_at).toLocaleString(zh ? 'zh-HK' : 'en-GB')}{!incoming && m.read_at ? (zh ? ' · 已讀' : ' · Read') : ''}</time>
                  </div>
                </div> })}
            </div>
            <form onSubmit={e => { e.preventDefault(); void send() }} className="flex gap-2 border-t border-border p-3">
              <input value={input} onChange={e => setInput(e.target.value)} maxLength={1000} placeholder={zh ? '輸入訊息（限合成資料）…' : 'Write a synthetic message…'}
                aria-label={zh ? '訊息內容' : 'Message'} className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm" />
              <button type="submit" disabled={sending || !input.trim()} className="rounded-lg bg-pink-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{zh ? '發送' : 'Send'}</button>
            </form>
          </> : <p className="m-auto p-5 text-sm text-muted-foreground">{zh ? '選擇一位員工開始對話。' : 'Choose a staff member.'}</p>}
        </section>
      </div>}
  </div>
}
