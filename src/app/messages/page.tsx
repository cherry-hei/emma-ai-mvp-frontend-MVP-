'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'
import { messagesApi, type DirectMessage, type MessageContact } from '@/lib/messages-api'

const PINK = '#E8187A'

export default function MessagesPage() {
  const { lang } = useLang()
  const { user } = useAuth()
  const isZH = lang === 'zh'
  const sessionKey = user ? `${user.userId}:${user.facilityId ?? ''}` : null
  const requestGeneration = useRef(0)
  const draftsByContact = useRef<Record<string, string>>({})

  const [contacts, setContacts] = useState<MessageContact[]>([])
  const [messages, setMessages] = useState<DirectMessage[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)

  const L = useMemo(() => ({
    title: isZH ? '訊息中心' : 'Messages',
    subtitle: isZH
      ? '與同機構已開戶的員工雙向溝通；系統通知和替更邀請是獨立資料。'
      : 'Two-way messages with provisioned staff in this facility; system notifications and cover offers are separate.',
    trial: isZH
      ? '僅供合成資料測試；未完成香港正式環境審批前，請勿輸入真實員工或院友資料。'
      : 'Synthetic-data evaluation only. Do not enter real staff or resident details before the Hong Kong production gate.',
    unavailable: isZH ? '訊息後端暫不可用或你沒有權限；訊息沒有儲存在本機。' : 'Message backend is unavailable or access is denied; no message was saved locally.',
    noContacts: isZH ? '暫未有可聯絡的已開戶員工。' : 'No provisioned staff contacts are available.',
    choose: isZH ? '選擇一位員工開始對話。' : 'Choose a staff member to start a conversation.',
    noMessages: isZH ? '未有對話，請開始輸入。' : 'No messages yet. Start typing below.',
    placeholder: isZH ? '輸入訊息（限合成資料）…' : 'Write a synthetic message…',
    send: isZH ? '發送' : 'Send',
    unread: isZH ? '未讀' : 'Unread',
    read: isZH ? '已讀' : 'Read',
  }), [isZH])

  // A late response from the previous login/facility must never paint over a new
  // session. apiFetch also has credential-generation protection for the request.
  useEffect(() => {
    requestGeneration.current += 1
    draftsByContact.current = {}
    setContacts([])
    setMessages([])
    setSelectedId(null)
    setInput('')
    setError('')
    setSending(false)
    setLoading(Boolean(sessionKey))
  }, [sessionKey])

  const load = useCallback(async (silent = false) => {
    if (!sessionKey) return
    const generation = requestGeneration.current
    if (!silent) setLoading(true)
    try {
      const [people, rows] = await Promise.all([messagesApi.contacts(), messagesApi.list()])
      if (generation !== requestGeneration.current) return
      setContacts(people)
      setMessages(rows)
      setError('')
    } catch (cause) {
      if (generation !== requestGeneration.current) return
      setContacts([])
      setMessages([])
      setSelectedId(null)
      setError(cause instanceof Error ? cause.message : 'Unable to load messages')
    } finally {
      if (generation === requestGeneration.current && !silent) setLoading(false)
    }
  }, [sessionKey])

  useEffect(() => {
    if (!sessionKey) return
    void load()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && navigator.onLine) void load(true)
    }, 30_000)
    return () => window.clearInterval(timer)
  }, [load, sessionKey])

  const knownMessages = useMemo(() => {
    const contactIds = new Set(contacts.map(contact => contact.id))
    return messages.filter(message =>
      contactIds.has(message.sender_profile_id) || contactIds.has(message.recipient_profile_id))
  }, [contacts, messages])

  const active = contacts.find(contact => contact.id === selectedId)
  const thread = active
    ? knownMessages.filter(message => message.sender_profile_id === active.id || message.recipient_profile_id === active.id)
      .sort((a, b) => a.created_at.localeCompare(b.created_at))
    : []

  const latestFor = (contactId: string) => knownMessages
    .filter(message => message.sender_profile_id === contactId || message.recipient_profile_id === contactId)
      .at(-1)

  async function open(contact: MessageContact) {
    if (sending) return
    const generation = requestGeneration.current
    if (selectedId) draftsByContact.current[selectedId] = input
    setSelectedId(contact.id)
    setInput(draftsByContact.current[contact.id] ?? '')
    const unread = knownMessages.filter(message => message.sender_profile_id === contact.id && !message.read_at)
    await Promise.allSettled(unread.map(message => messagesApi.markRead(message.id)))
    if (unread.length && generation === requestGeneration.current) await load(true)
  }

  async function send() {
    if (!active || !input.trim() || sending) return
    const generation = requestGeneration.current
    const contactId = active.id
    setSending(true)
    try {
      await messagesApi.send(contactId, input.trim())
      if (generation !== requestGeneration.current) return
      delete draftsByContact.current[contactId]
      setInput('')
      await load(true)
    } catch (cause) {
      if (generation === requestGeneration.current) setError(cause instanceof Error ? cause.message : 'Message not sent')
    } finally {
      if (generation === requestGeneration.current) setSending(false)
    }
  }

  return (
    <div className="flex h-full flex-col gap-4 p-4 md:p-5">
      <header>
        <h1 className="text-lg font-bold text-gray-900">{L.title}</h1>
        <p className="mt-0.5 text-[11px] text-gray-500">{L.subtitle}</p>
        <p className="mt-1 text-[11px] font-medium text-rose-700">{L.trial}</p>
      </header>

      {error && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
        {error} · {L.unavailable}
      </div>}

      {loading ? <p className="text-sm text-gray-500">{isZH ? '載入中…' : 'Loading…'}</p> : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 md:grid-cols-[240px_1fr]">
          <aside className="min-h-28 overflow-y-auto rounded-xl border border-gray-200 bg-white p-2" aria-label={isZH ? '可聯絡員工' : 'Contacts'}>
            {!contacts.length && <p className="p-3 text-sm text-gray-500">{L.noContacts}</p>}
            {contacts.map(contact => {
              const latest = latestFor(contact.id)
              const unread = knownMessages.filter(message => message.sender_profile_id === contact.id && !message.read_at).length
              return <button key={contact.id} type="button" disabled={sending} onClick={() => void open(contact)} aria-pressed={selectedId === contact.id}
                className={`mb-1 block w-full rounded-lg p-3 text-left text-sm ${selectedId === contact.id ? 'bg-pink-50 text-pink-900' : 'hover:bg-gray-50'}`}>
                <strong className="block truncate">{contact.display_name}</strong>
                <span className="block truncate text-xs text-gray-500">{latest?.body || (isZH ? '開始對話' : 'Start a conversation')}</span>
                {unread > 0 && <span className="text-xs font-bold text-pink-700">{L.unread}</span>}
              </button>
            })}
          </aside>

          <section className="flex min-h-[360px] flex-col overflow-hidden rounded-xl border border-gray-200 bg-white">
            {active ? <>
              <div className="border-b border-gray-100 p-3 text-sm font-semibold text-gray-900">{active.display_name}</div>
              <div className="flex-1 space-y-3 overflow-y-auto bg-gray-50 p-4" aria-live="polite">
                {!thread.length && <p className="text-sm text-gray-500">{L.noMessages}</p>}
                {thread.map(message => {
                  const incoming = message.sender_profile_id === active.id
                  return <div key={message.id} className={`flex ${incoming ? 'justify-start' : 'justify-end'}`}>
                    <div className={`max-w-[85%] rounded-xl p-3 text-sm ${incoming ? 'border border-gray-200 bg-white text-gray-900' : 'text-white'}`} style={incoming ? undefined : { background: PINK }}>
                      <p className="whitespace-pre-wrap break-words">{message.body}</p>
                      <time dateTime={message.created_at} className="mt-1 block text-[10px] opacity-80">
                        {new Date(message.created_at).toLocaleString(isZH ? 'zh-HK' : 'en-GB')}
                        {!incoming && message.read_at ? ` · ${L.read}` : ''}
                      </time>
                    </div>
                  </div>
                })}
              </div>
              <form onSubmit={event => { event.preventDefault(); void send() }} className="flex gap-2 border-t border-gray-100 p-3">
                <input value={input} disabled={sending} onChange={event => { setInput(event.target.value); if (selectedId) draftsByContact.current[selectedId] = event.target.value }} maxLength={1000} placeholder={L.placeholder}
                  aria-label={isZH ? '訊息內容' : 'Message'} className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-pink-200" />
                <button type="submit" disabled={sending || !input.trim()} className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-40" style={{ background: PINK }}>{L.send}</button>
              </form>
            </> : <p className="m-auto p-5 text-sm text-gray-500">{L.choose}</p>}
          </section>
        </div>
      )}
    </div>
  )
}
