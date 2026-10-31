'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLang } from '@/components/layout/LanguageContext'
import { useAuth } from '@/components/layout/AuthContext'
import { messagesApi, type DirectMessage, type MessageContact } from '@/lib/messages-api'

const MAX_MESSAGE_LENGTH = 1_000
const POLL_INTERVAL_MS = 30_000

function mergeMessages(current: DirectMessage[], incoming: DirectMessage[]): DirectMessage[] {
  // Every entry in this union originated from the service. Keeping a confirmed
  // write prevents an older poll response from erasing it while replicas catch up.
  const byId = new Map<string, DirectMessage>()
  current.forEach((message) => byId.set(message.id, message))
  incoming.forEach((message) => byId.set(message.id, message))
  return [...byId.values()].sort((a, b) => a.created_at.localeCompare(b.created_at))
}

function messageTime(value: string, lang: 'en' | 'zh'): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(lang === 'zh' ? 'zh-Hant' : 'en-SG', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

type MessageIssue = 'load' | 'send' | 'read' | null

export default function MessagesPage() {
  const { lang } = useLang()
  const { status, user } = useAuth()
  const isZH = lang === 'zh'

  // `apiFetch` supplies the JWT. This identity key supplies the UI-level stale
  // response guard and is deliberately based on both identity and facility.
  const sessionKey = status === 'authed' && user?.userId && user.facilityId
    ? `${user.userId}:${user.facilityId}`
    : null
  const hasFacilityContext = status === 'authed' && Boolean(user?.userId && user.facilityId)

  const requestGeneration = useRef(0)
  const loadRequest = useRef(0)
  const openRequest = useRef(0)
  const sendRequest = useRef(0)
  const contentGeneration = useRef(0)
  const sendingRef = useRef(false)
  const selectedIdRef = useRef<string | null>(null)
  const inputRef = useRef('')
  const draftsByContact = useRef<Record<string, string>>({})

  const [contacts, setContacts] = useState<MessageContact[]>([])
  const [messages, setMessages] = useState<DirectMessage[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [issue, setIssue] = useState<MessageIssue>(null)

  const L = useMemo(() => isZH ? {
    title: '訊息中心',
    subtitle: '與同一院舍已開通帳戶的同事直接聯絡。',
    privacyNote: '訊息只會使用已登入帳戶及院舍範圍的服務；此頁不會建立示範對話或把訊息儲存在瀏覽器。',
    contacts: '已開通的聯絡人',
    noContacts: '暫未有可聯絡的已開通帳戶。',
    select: '選擇一位聯絡人以查看對話。',
    back: '返回聯絡人',
    loading: '正在載入訊息…',
    noMessages: '暫未有訊息。',
    placeholder: '輸入訊息…',
    send: '發送',
    sending: '發送中…',
    read: '已讀',
    unread: '未讀',
    retry: '重試',
    signInRequired: '請使用已驗證的帳戶登入後查看訊息。',
    facilityRequired: '此帳戶未有院舍範圍，因此無法載入訊息。',
    unavailable: '此環境暫時無法使用訊息服務。需要部署已提議的訊息 API 路由並為你的帳戶開通權限；沒有訊息已儲存在本機。',
    sendFailed: '伺服器未確認此訊息。你的草稿仍然保留，服務恢復後可再次發送。',
    readFailed: '伺服器未確認已讀狀態；訊息可能仍然顯示為未讀。',
    composerLabel: '給 {name} 的訊息',
    length: '最多 {count} 個字元',
  } : {
    title: 'Messages',
    subtitle: 'Direct contact with provisioned accounts in the same facility.',
    privacyNote: 'Messages use the signed-in account and facility-scoped service only; this page creates no demo conversations and stores none in the browser.',
    contacts: 'Provisioned contacts',
    noContacts: 'No provisioned contacts are available.',
    select: 'Choose a contact to view the conversation.',
    back: 'Back to contacts',
    loading: 'Loading messages…',
    noMessages: 'No messages yet.',
    placeholder: 'Write a message…',
    send: 'Send',
    sending: 'Sending…',
    read: 'Read',
    unread: 'Unread',
    retry: 'Retry',
    signInRequired: 'Sign in with an authenticated account to view messages.',
    facilityRequired: 'This account has no facility context, so messages cannot be loaded.',
    unavailable: 'Messaging is unavailable in this environment. The proposed messaging API routes must be deployed and your account provisioned; no message was stored on this device.',
    sendFailed: 'The server did not confirm this message. Your draft is kept so you can send it again when the service is available.',
    readFailed: 'The server did not confirm the read status; the message may remain unread.',
    composerLabel: 'Message to {name}',
    length: 'Up to {count} characters',
  }, [isZH])

  const rememberDraft = useCallback((contactId: string, value = inputRef.current) => {
    draftsByContact.current[contactId] = value
  }, [])

  const setDraft = useCallback((value: string) => {
    inputRef.current = value
    setInput(value)
  }, [])

  const load = useCallback(async (silent = false, allowDuringSend = false) => {
    if (!sessionKey || (sendingRef.current && !allowDuringSend)) return

    const generation = requestGeneration.current
    const contentVersion = contentGeneration.current
    const request = ++loadRequest.current
    if (!silent) setLoading(true)

    try {
      const [nextContacts, nextMessages] = await Promise.all([
        messagesApi.contacts(),
        messagesApi.list(),
      ])
      if (generation !== requestGeneration.current ||
          request !== loadRequest.current ||
          contentVersion !== contentGeneration.current) return

      setContacts(nextContacts)
      setMessages((current) => mergeMessages(current, nextMessages))
      const currentSelection = selectedIdRef.current
      if (currentSelection && !nextContacts.some((contact) => contact.id === currentSelection)) {
        rememberDraft(currentSelection)
        selectedIdRef.current = null
        setSelectedId(null)
        setDraft('')
      }
      setIssue(null)
    } catch {
      if (generation !== requestGeneration.current || request !== loadRequest.current) return
      // Do not replace confirmed service data with empty placeholders after a
      // transient failure. The visible alert and retry remain explicit.
      setIssue('load')
    } finally {
      if (generation === requestGeneration.current && request === loadRequest.current && !silent) {
        setLoading(false)
      }
    }
  }, [rememberDraft, sessionKey, setDraft])

  // A real identity or tenant change invalidates every in-flight response and is
  // the only event that discards all memory-only drafts.
  useEffect(() => {
    requestGeneration.current += 1
    loadRequest.current += 1
    openRequest.current += 1
    sendRequest.current += 1
    contentGeneration.current += 1
    sendingRef.current = false
    draftsByContact.current = {}
    selectedIdRef.current = null
    inputRef.current = ''
    setContacts([])
    setMessages([])
    setSelectedId(null)
    setInput('')
    setIssue(null)
    setSending(false)
    setLoading(Boolean(sessionKey))
  }, [sessionKey])

  useEffect(() => {
    if (!sessionKey) return
    void load()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && navigator.onLine) void load(true)
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [load, sessionKey])

  const knownMessages = useMemo(() => {
    const contactIds = new Set(contacts.map((contact) => contact.id))
    return messages.filter((message) =>
      contactIds.has(message.sender_profile_id) || contactIds.has(message.recipient_profile_id))
  }, [contacts, messages])

  const active = contacts.find((contact) => contact.id === selectedId) ?? null
  const thread = useMemo(() => active
    ? knownMessages.filter((message) =>
      message.sender_profile_id === active.id || message.recipient_profile_id === active.id)
    : [], [active, knownMessages])

  const latestFor = useCallback((contactId: string) => knownMessages
    .filter((message) => message.sender_profile_id === contactId || message.recipient_profile_id === contactId)
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .at(-1), [knownMessages])

  const unreadFor = useCallback((contactId: string) => knownMessages
    .filter((message) => message.sender_profile_id === contactId && !message.read_at), [knownMessages])

  const openContact = useCallback((contact: MessageContact) => {
    if (sendingRef.current) return

    const previous = selectedIdRef.current
    if (previous && previous !== contact.id) rememberDraft(previous)
    selectedIdRef.current = contact.id
    setSelectedId(contact.id)
    setDraft(draftsByContact.current[contact.id] ?? '')

    const unread = unreadFor(contact.id)
    if (!unread.length) return

    const generation = requestGeneration.current
    const viewRequest = ++openRequest.current
    contentGeneration.current += 1
    void (async () => {
      try {
        const confirmations = await Promise.all(unread.map((message) => messagesApi.markRead(message.id)))
        const confirmed = confirmations.every((message, index) =>
          message.id === unread[index].id &&
          message.sender_profile_id === contact.id &&
          message.read_at !== null)
        if (!confirmed) throw new Error('Read status was not confirmed.')
        if (generation !== requestGeneration.current ||
            viewRequest !== openRequest.current ||
            selectedIdRef.current !== contact.id) return
        // A confirmed response is re-read before the UI renders a read receipt.
        // Retire any poll that began while this status update was pending.
        contentGeneration.current += 1
        void load(true)
      } catch {
        if (generation !== requestGeneration.current ||
            viewRequest !== openRequest.current ||
            selectedIdRef.current !== contact.id) return
        setIssue('read')
      }
    })()
  }, [load, rememberDraft, setDraft, unreadFor])

  const closeContact = useCallback(() => {
    if (sendingRef.current || !selectedIdRef.current) return
    rememberDraft(selectedIdRef.current)
    openRequest.current += 1
    selectedIdRef.current = null
    setSelectedId(null)
    setDraft('')
    setIssue(null)
  }, [rememberDraft, setDraft])

  const updateDraft = useCallback((value: string) => {
    setDraft(value)
    if (selectedIdRef.current) rememberDraft(selectedIdRef.current, value)
    if (issue === 'send') setIssue(null)
  }, [issue, rememberDraft, setDraft])

  const send = useCallback(async () => {
    if (!active || sendingRef.current) return
    const body = inputRef.current.trim()
    if (!body || body.length > MAX_MESSAGE_LENGTH) return

    const generation = requestGeneration.current
    const request = ++sendRequest.current
    const contactId = active.id
    sendingRef.current = true
    contentGeneration.current += 1
    setSending(true)
    setIssue(null)

    try {
      const confirmed = await messagesApi.send(contactId, body)
      if (confirmed.recipient_profile_id !== contactId || confirmed.body !== body) {
        throw new Error('Message confirmation did not match the selected contact.')
      }
      if (generation !== requestGeneration.current ||
          request !== sendRequest.current ||
          selectedIdRef.current !== contactId) return

      // Retire a poll that began while this write awaited confirmation, then
      // preserve the confirmed response until a newer service read completes.
      contentGeneration.current += 1
      setMessages((current) => mergeMessages(current, [confirmed]))
      delete draftsByContact.current[contactId]
      setDraft('')
      // The write response, rather than an optimistic placeholder, is the only
      // source used here. Refresh in the background for other-server updates.
      void load(true, true)
    } catch {
      if (generation !== requestGeneration.current ||
          request !== sendRequest.current ||
          selectedIdRef.current !== contactId) return
      // Keep both the uncontrolled memory copy and the visible draft intact.
      rememberDraft(contactId)
      setIssue('send')
    } finally {
      if (generation === requestGeneration.current && request === sendRequest.current) {
        sendingRef.current = false
        setSending(false)
      }
    }
  }, [active, load, rememberDraft, setDraft])

  const issueText = issue === 'send' ? L.sendFailed : issue === 'read' ? L.readFailed : L.unavailable
  const accessMessage = status !== 'authed' ? L.signInRequired : !hasFacilityContext ? L.facilityRequired : null
  const showChat = Boolean(active)

  return (
    <div className="h-full min-h-0 p-3 sm:p-5">
      <div className="mx-auto flex h-[calc(100dvh-7.75rem)] max-w-6xl overflow-hidden rounded-2xl border border-pink-100 bg-white shadow-sm md:h-[calc(100dvh-6rem)]">
        <section className={`${showChat ? 'hidden md:flex' : 'flex'} min-w-0 w-full flex-col border-r border-pink-100 md:w-[min(340px,36vw)] md:flex-none`} aria-label={L.contacts}>
          <header className="border-b border-pink-100 px-4 py-4 sm:px-5">
            <h1 className="text-lg font-bold text-slate-900">{L.title}</h1>
            <p className="emma-reflow-text mt-0.5 break-words text-xs text-slate-500 [overflow-wrap:anywhere]">{L.subtitle}</p>
            <p className="emma-reflow-text mt-3 break-words rounded-xl border border-pink-100 bg-pink-50 px-3 py-2 text-[11px] leading-relaxed text-slate-600 [overflow-wrap:anywhere]">{L.privacyNote}</p>
          </header>

          {accessMessage ? <div role="alert" className="m-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm leading-relaxed text-amber-900">{accessMessage}</div> : null}
          {issue ? <div role="alert" className="m-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm leading-relaxed text-rose-800">
            <p>{issueText}</p>
            {sessionKey ? <button type="button" onClick={() => void load()} disabled={loading || sending} className="mt-2 text-xs font-semibold text-rose-800 underline decoration-rose-300 underline-offset-2 disabled:opacity-50">{L.retry}</button> : null}
          </div> : null}

          <div className="min-h-0 flex-1 overflow-y-auto p-2" aria-busy={loading}>
            {loading && contacts.length === 0 ? <p className="p-3 text-sm text-slate-500">{L.loading}</p> : null}
            {!loading && sessionKey && contacts.length === 0 && !issue ? <p className="p-3 text-sm text-slate-500">{L.noContacts}</p> : null}
            {contacts.map((contact) => {
              const latest = latestFor(contact.id)
              const unread = unreadFor(contact.id).length
              const selected = contact.id === selectedId
              return <button
                key={contact.id}
                type="button"
                onClick={() => openContact(contact)}
                disabled={sending}
                aria-pressed={selected}
                className={`mb-1 w-full rounded-xl px-3 py-3 text-left transition focus:outline-none focus:ring-2 focus:ring-pink-200 disabled:cursor-not-allowed ${selected ? 'bg-pink-50' : 'hover:bg-slate-50'}`}
              >
                <div className="flex min-w-0 items-start justify-between gap-2">
                  <span className={`emma-reflow-text min-w-0 break-words text-sm font-semibold [overflow-wrap:anywhere] ${selected ? 'text-pink-700' : 'text-slate-900'}`}>{contact.display_name}</span>
                  {unread > 0 ? <span className="shrink-0 rounded-full bg-pink-600 px-2 py-0.5 text-[10px] font-semibold text-white">{unread} {L.unread}</span> : null}
                </div>
                <p className="emma-reflow-text mt-1 break-words text-xs text-slate-500 [overflow-wrap:anywhere]">{contact.role}</p>
                <p className="emma-reflow-text mt-1 line-clamp-2 break-words text-xs text-slate-500 [overflow-wrap:anywhere]">{latest?.body || L.noMessages}</p>
              </button>
            })}
          </div>
        </section>

        <section className={`${showChat ? 'flex' : 'hidden md:flex'} min-w-0 flex-1 flex-col`} aria-live="polite">
          {!active ? <div className="m-auto max-w-md px-6 text-center text-sm leading-relaxed text-slate-500">{accessMessage || L.select}</div> : <>
            <header className="border-b border-pink-100 bg-white px-4 py-3 sm:px-5">
              <button type="button" onClick={closeContact} disabled={sending} className="mb-2 text-xs font-semibold text-pink-700 md:hidden disabled:opacity-50">{L.back}</button>
              <div className="min-w-0">
                <h2 className="emma-reflow-text break-words text-base font-bold text-slate-900 [overflow-wrap:anywhere]">{active.display_name}</h2>
                <p className="emma-reflow-text mt-0.5 break-words text-xs text-slate-500 [overflow-wrap:anywhere]">{active.role}</p>
              </div>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto bg-pink-50/40 px-4 py-4 sm:px-5">
              {loading ? <p className="mb-3 text-xs text-slate-500">{L.loading}</p> : null}
              {!loading && thread.length === 0 ? <p className="mt-10 text-center text-sm text-slate-500">{L.noMessages}</p> : null}
              <div className="space-y-3">
                {thread.map((message) => {
                  const incoming = message.sender_profile_id === active.id
                  return <article key={message.id} className={`flex min-w-0 ${incoming ? 'justify-start' : 'justify-end'}`}>
                    <div className={`min-w-0 max-w-[88%] rounded-2xl px-3.5 py-2.5 shadow-sm sm:max-w-[72%] ${incoming ? 'rounded-bl-md border border-slate-200 bg-white text-slate-800' : 'rounded-br-md bg-pink-600 text-white'}`}>
                      <p className="emma-reflow-text whitespace-pre-wrap break-words text-sm leading-relaxed [overflow-wrap:anywhere]">{message.body}</p>
                      <time dateTime={message.created_at} className={`mt-1 block text-[10px] ${incoming ? 'text-slate-400' : 'text-pink-100'}`}>
                        {messageTime(message.created_at, lang)}{!incoming && message.read_at ? ` · ${L.read}` : ''}
                      </time>
                    </div>
                  </article>
                })}
              </div>
            </div>

            <form onSubmit={(event) => { event.preventDefault(); void send() }} className="border-t border-pink-100 bg-white p-3 sm:p-4">
              {issue ? <div role="alert" className="emma-reflow-wrap mb-2 flex flex-wrap items-start justify-between gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs leading-relaxed text-rose-800">
                <span className="emma-reflow-text min-w-0 flex-1 break-words [overflow-wrap:anywhere]">{issueText}</span>
                {sessionKey ? <button type="button" onClick={() => void load()} disabled={loading || sending} className="shrink-0 font-semibold underline disabled:opacity-50">{L.retry}</button> : null}
              </div> : null}
              <label htmlFor="message-body" className="sr-only">{L.composerLabel.replace('{name}', active.display_name)}</label>
              <textarea
                id="message-body"
                rows={3}
                value={input}
                maxLength={MAX_MESSAGE_LENGTH}
                disabled={sending || loading || !sessionKey}
                onChange={(event) => updateDraft(event.target.value)}
                placeholder={L.placeholder}
                className="block min-h-[5rem] w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-pink-400 focus:ring-2 focus:ring-pink-100 disabled:bg-slate-50"
              />
              <div className="emma-reflow-wrap mt-2 flex flex-wrap items-center justify-between gap-2">
                <span className="emma-reflow-text min-w-0 flex-1 break-words text-[11px] text-slate-400 [overflow-wrap:anywhere]">{input.length}/{MAX_MESSAGE_LENGTH} · {L.length.replace('{count}', String(MAX_MESSAGE_LENGTH))}</span>
                <button type="submit" disabled={sending || loading || !sessionKey || !input.trim() || input.trim().length > MAX_MESSAGE_LENGTH} className="shrink-0 rounded-xl bg-pink-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-pink-700 disabled:cursor-not-allowed disabled:bg-slate-300">{sending ? L.sending : L.send}</button>
              </div>
            </form>
          </>}
        </section>
      </div>
    </div>
  )
}
